import copy
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User, Run, Turn, City, Seeker
from ..telegram_auth import get_tg_user
from ..config import (FREE_TURNS_PER_DAY, CONTEXT_RECENT_TURNS, SUMMARIZE_EVERY,
                      RUNS_PER_WINDOW, RUN_WINDOW_HOURS)
from ..game import rules, state as state_mod, master
from ..game.dungeons import DUNGEONS, get_dungeon, DEFAULT_DUNGEON

router = APIRouter(prefix="/api", tags=["game"])


def _server_version() -> str:
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent.parent
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True,
            stderr=subprocess.DEVNULL, cwd=root,
        ).strip()
    except Exception:
        pass
    try:  # git-бинаря нет в PATH (так бывает у workflow) — читаем .git руками
        head = (root / ".git" / "HEAD").read_text().strip()
        if head.startswith("ref:"):
            ref = head.split(" ", 1)[1]
            return (root / ".git" / ref).read_text().strip()[:7]
        return head[:7]
    except Exception:
        return "unknown"


SERVER_VERSION = _server_version()


# ---------- helpers ----------

def _get_or_create_user(db: Session, tg: dict) -> User:
    user = db.query(User).filter(User.tg_id == tg["id"]).first()
    if not user:
        user = User(tg_id=tg["id"], username=tg.get("username"), first_name=tg.get("first_name"))
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _check_turn_limit(db: Session, user: User):
    today = date.today()
    if user.turns_date != today:
        user.turns_date = today
        user.turns_today = 0
    if user.turns_today >= FREE_TURNS_PER_DAY:
        raise HTTPException(429, f"Лимит ходов на сегодня исчерпан ({FREE_TURNS_PER_DAY}). Возвращайся завтра.")
    user.turns_today += 1
    db.commit()


from .city import get_or_create_city as _get_or_create_city, city_payload as _full_city_payload
from ..game.buildings import seeker_slots


def _city_payload(city: City) -> dict:
    from ..game.resources import res_brief
    return {"buildings": city.buildings, "gold": city.gold,
            "resources": city.resources, "resources_named": res_brief(city.resources)}


def _finish_seeker(db: Session, run: Run, died: bool, final_state: dict):
    """Синхронизировать персистентного искателя с исходом забега."""
    if not run.seeker_id:
        return
    s = db.query(Seeker).filter(Seeker.id == run.seeker_id).first()
    if not s:
        return
    if died:
        s.status = "dead"
    else:
        s.status = "idle"
        s.level = final_state.get("level", s.level)
        s.xp = final_state.get("xp", s.xp)
        s.max_hp = final_state.get("max_hp", s.max_hp)
        s.runs_survived += 1
        s.equipment = final_state.get("equipment", s.equipment) or {}  # износ/поломки сохраняются
        s.inventory = final_state.get("inventory", s.inventory) or []   # найденное остаётся при нём
        s.stats = final_state.get("stats", s.stats)
        s.talents = final_state.get("talents", s.talents) or []
        s.stat_points = int(final_state.get("stat_points", 0))
        s.talent_points = int(final_state.get("talent_points", 0))


def _active_run(db: Session, user: User) -> Run | None:
    return (
        db.query(Run)
        .filter(Run.user_id == user.id, Run.status == "active")
        .order_by(Run.id.desc())
        .first()
    )


def _run_payload(run: Run, last: dict | None = None) -> dict:
    return {
        "run_id": run.id,
        "dungeon": run.dungeon or DEFAULT_DUNGEON,
        "status": run.status,
        "death_cause": run.death_cause,
        "state": run.state,
        "turn_count": run.turn_count,
        "last": last,
    }


def _apply_gm_result(db: Session, run: Run, player_input: str, result: dict) -> dict:
    # deepcopy обязателен: изменение только вложенных структур (рюкзак/сцена/инвентарь)
    # при shallow-копии не считалось изменением атрибута и не попадало в базу
    level_before = int(run.state.get("level", 1))
    new_state = state_mod.apply_delta(copy.deepcopy(run.state), result.get("state_delta") or {})
    if new_state.get("level", 1) > level_before:
        note = f"\n\n⬆ УРОВЕНЬ {new_state['level']}! Раны затягиваются. +1 очко характеристик"
        if new_state["level"] % 2 == 0:
            note += " и выбор таланта"
        note += " — раскрой лист персонажа."
        result["narration"] = result.get("narration", "").rstrip() + note
    extracted = bool(result.get("extracted")) and new_state["hp"] > 0
    game_over = (bool(result.get("game_over")) or new_state["hp"] <= 0) and not extracted

    # Очко судьбы: один раз за забег смертельный исход превращается в чудом-выжил с 1 HP
    if game_over and new_state.get("fate", 0) > 0:
        new_state["fate"] = 0
        new_state["hp"] = 1
        game_over = False
        result["narration"] = (result.get("narration", "").rstrip() +
            "\n\nТьма уже тянет к тебе пальцы — но судьба вцепляется в ворот и выдёргивает "
            "обратно. Ты жив. Едва. Второго чуда не будет.")

    # Свиток последнего вздоха: серверная гарантия, срабатывает после судьбы
    from ..game.magic import LASTBREATH_NAME
    if game_over and LASTBREATH_NAME in (new_state.get("inventory") or []):
        new_state["inventory"] = [i for i in new_state["inventory"] if i != LASTBREATH_NAME]
        new_state["hp"] = 1
        game_over = False
        result["narration"] = (result.get("narration", "").rstrip() +
            "\n\nСвиток на поясе вспыхивает сам собой. Мир возвращается со вкусом пепла во рту: "
            "работа Финеуса выдернула тебя за миг до конца. Пергамент осыпался золой.")

    # Каменная кожа тикает: минус ход каждый ход
    ss = int((new_state.get("flags") or {}).get("stone_skin", 0) or 0)
    if ss > 0:
        new_state["flags"]["stone_skin"] = ss - 1

    _ART_TAGS = {
        # общие
        "gates","stairs","skull","goblin","rat","undead","cultist","merchant",
        "chest","altar","potion","well","torch","boss",
        "spider","ghost","door","key","campfire","bones",
        # Кар-Морд
        "forge_dungeon","gold_vein","lift","cavein","flooded_hall","priest",
        # Прелый Лес
        "forest","wolf","rootwalker","witch_hut","swamp_lights","hanging_oak","pastor",
        # Обитель
        "scriptorium","bell","cage","stitched","candles","archimandrite",
    }
    art = result.get("scene_art")
    art = art if art in _ART_TAGS else None
    if art:
        # не повторять арт, который уже был в последних 8 ходах
        recent_art = {
            t[0] for t in db.query(Turn.scene_art)
            .filter(Turn.run_id == run.id, Turn.scene_art != None)  # noqa: E711
            .order_by(Turn.id.desc()).limit(8).all()
        }
        if art in recent_art:
            art = None
    turn = Turn(
        run_id=run.id,
        player_input=player_input,
        narration=result["narration"],
        rolls=result.get("rolls", []),
        suggested_actions=result.get("suggested_actions", []),
        state_delta=result.get("state_delta", {}),
        scene_art=art,
    )
    db.add(turn)
    run.state = new_state
    run.turn_count += 1

    if extracted:
        run.status = "extracted"
        user = run.user
        user.total_runs += 1
        user.deepest_level = max(user.deepest_level, new_state.get("depth", 1))
        user.best_gold = max(user.best_gold, new_state.get("gold", 0))
        # лут уезжает в вечный город
        city = _get_or_create_city(db, user)
        cres = dict(city.resources or {})
        hauled = (new_state.get("backpack") or {}).get("res", {}) or {}
        for rid, cnt in hauled.items():
            cres[rid] = cres.get(rid, 0) + int(cnt)
        city.resources = cres
        city.gold = (city.gold or 0) + int(new_state.get("gold", 0))
        # выжившие соратники возвращаются в таверну с +1 преданности
        back = []
        for m in new_state.get("party", []):
            m = dict(m)
            m["loyalty"] = int(m.get("loyalty", 0)) + 1
            m["hp"] = m.get("max_hp", m.get("hp", 8))
            back.append(m)
        city.companions = (list(city.companions or []) + back)
        # сюжетные флаги, пережившие подземелье
        cflags = dict(city.flags or {})
        for f in ("dwarf_saved", "mage_saved"):
            if (new_state.get("flags") or {}).get(f):
                cflags[f] = True
        if user.total_runs >= 2:
            cflags.setdefault("barman_dead", True)  # старик не дождался третьей ходки
        city.flags = cflags
        _finish_seeker(db, run, died=False, final_state=new_state)

    if game_over:
        run.status = "dead"
        run.death_cause = result.get("death_cause") or "Погиб в глубинах Кар-Морда"
        user = run.user
        user.total_runs += 1
        user.deepest_level = max(user.deepest_level, new_state.get("depth", 1))
        user.best_gold = max(user.best_gold, new_state.get("gold", 0))
        _finish_seeker(db, run, died=True, final_state=new_state)
        # соратники, бывшие с искателем, сгинули вместе с ним

    db.commit()

    # rolling summary: fold old turns so context (and cost) stays flat
    if run.status == "active" and run.turn_count % SUMMARIZE_EVERY == 0:
        to_fold = (
            db.query(Turn)
            .filter(Turn.run_id == run.id, Turn.summarized == False)  # noqa: E712
            .order_by(Turn.id)
            .all()
        )[:-CONTEXT_RECENT_TURNS or None]
        if to_fold:
            try:
                run.summary = master.summarize(run.summary or "", to_fold)
                for t in to_fold:
                    t.summarized = True
                db.commit()
            except Exception:
                db.rollback()  # summary failure must never kill the game

    payload = _run_payload(run, last={
        "narration": result["narration"],
        "suggested_actions": result.get("suggested_actions", []),
        "rolls": result.get("rolls", []),
        "scene_art": art,
    })
    if extracted:
        payload["hauled"] = (new_state.get("backpack") or {}).get("res", {})
        payload["city"] = _city_payload(_get_or_create_city(db, run.user))
    return payload


# ---------- schemas ----------

class NewRunIn(BaseModel):
    # либо seeker_id существующего, либо параметры нового искателя
    dungeon: str = DEFAULT_DUNGEON
    seeker_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=24)
    race: str | None = None
    cls: str | None = Field(default=None, alias="class")

    class Config:
        populate_by_name = True


class TurnIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


# ---------- endpoints ----------

@router.get("/meta")
def meta():
    return {
        "races": {k: v["name"] for k, v in rules.RACES.items()},
        "classes": {k: {"name": v["name"], "desc": v["desc"]} for k, v in rules.CLASSES.items()},
        "free_turns_per_day": FREE_TURNS_PER_DAY,
        "server_version": SERVER_VERSION,
        "talents": {
            tid: {"name": t["name"], "desc": t["desc"]}
            for tid, t in __import__("server.game.talents", fromlist=["TALENTS"]).TALENTS.items()
        },
        "dungeons": [
            {"id": did, "name": d["name"], "desc": d["desc"], "danger": d["danger"]}
            for did, d in DUNGEONS.items()
        ],
    }


@router.get("/me")
def me(tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    user = _get_or_create_user(db, tg)
    run = _active_run(db, user)
    payload = None
    if run:
        turns = db.query(Turn).filter(Turn.run_id == run.id).order_by(Turn.id).all()
        payload = _run_payload(run)
        payload["log"] = [
            {
                "player_input": t.player_input,
                "narration": t.narration,
                "rolls": t.rolls,
                "suggested_actions": t.suggested_actions,
                "scene_art": t.scene_art,
            }
            for t in turns[-20:]
        ]
    return {
        "city": _city_payload(_get_or_create_city(db, user)),
        "user": {
            "first_name": user.first_name,
            "turns_left": max(0, FREE_TURNS_PER_DAY - (user.turns_today if user.turns_date == date.today() else 0)),
            "total_runs": user.total_runs,
            "deepest_level": user.deepest_level,
            "best_gold": user.best_gold,
        },
        "run": payload,
    }


@router.post("/run/new")
def new_run(body: NewRunIn, tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    user = _get_or_create_user(db, tg)
    if _active_run(db, user):
        raise HTTPException(409, "У тебя уже есть активный забег. Заверши его или погибни с честью.")
    _check_turn_limit(db, user)

    city = _get_or_create_city(db, user)
    # кулдаун попыток: RUNS_PER_WINDOW за окно; трон сокращает окно на час за уровень (мин. 2ч)
    from datetime import datetime, timedelta
    window_h = max(2, RUN_WINDOW_HOURS - int((city.buildings or {}).get("throne", 0)))
    now = datetime.utcnow()
    stamps = [s for s in (user.run_stamps or [])
              if now - datetime.fromisoformat(s) < timedelta(hours=window_h)]
    if len(stamps) >= RUNS_PER_WINDOW:
        oldest = min(datetime.fromisoformat(s) for s in stamps)
        wait = oldest + timedelta(hours=window_h) - now
        h, m = int(wait.total_seconds() // 3600), int(wait.total_seconds() % 3600 // 60)
        raise HTTPException(429, f"Подземелья закрыты: попытки исчерпаны. Следующая через {h}ч {m:02d}м.")
    user.run_stamps = stamps + [now.isoformat()]
    if body.dungeon not in DUNGEONS:
        raise HTTPException(422, "Неизвестное подземелье")
    dungeon = get_dungeon(body.dungeon)
    if body.seeker_id:
        seeker = db.query(Seeker).filter(
            Seeker.id == body.seeker_id, Seeker.user_id == user.id, Seeker.status == "idle"
        ).first()
        if not seeker:
            raise HTTPException(404, "Искатель не найден или занят")
        char = rules.seeker_to_state(seeker, dungeon)
    else:
        if not (body.name and body.race and body.cls):
            raise HTTPException(422, "Для нового искателя нужны имя, раса и класс")
        living = db.query(Seeker).filter(
            Seeker.user_id == user.id, Seeker.status != "dead"
        ).count()
        if living >= seeker_slots(city.buildings):
            raise HTTPException(409, "Все слоты искателей заняты. Отправь живого или улучши Тронный зал.")
        try:
            char = rules.new_character(body.name, body.race, body.cls, dungeon)
        except ValueError:
            raise HTTPException(422, "Неизвестная раса или класс")
        seeker = Seeker(user_id=user.id, name=char["name"], race=char["race"], cls=char["class"],
                        level=1, xp=0, stats=char["stats"], max_hp=char["max_hp"],
                        inventory=list(char["inventory"]))
        db.add(seeker)
        db.flush()
    seeker.status = "in_run"
    # дружина из таверны идёт с искателем; город на время пустеет
    char["party"] = [dict(c) for c in (city.companions or [])]
    city.companions = []

    run = Run(user_id=user.id, seeker_id=seeker.id, state=char, dungeon=body.dungeon)
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        result = master.opening_scene(char, dungeon_id=body.dungeon)
    except Exception:
        import traceback
        traceback.print_exc()
        user.turns_today = max(0, user.turns_today - 1)
        run.status = "abandoned"
        db.commit()
        raise HTTPException(502, "Подземелье не отозвалось — сбой связи. Ход не списан, попробуй ещё раз.")
    return _apply_gm_result(db, run, "[начало забега]", result)


@router.post("/run/{run_id}/turn")
def make_turn(run_id: int, body: TurnIn, tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    user = _get_or_create_user(db, tg)
    run = db.query(Run).filter(Run.id == run_id, Run.user_id == user.id).first()
    if not run:
        raise HTTPException(404, "Забег не найден")
    if run.status != "active":
        raise HTTPException(409, "Этот забег окончен. Пермасмерть — это навсегда.")
    _check_turn_limit(db, user)

    recent = (
        db.query(Turn)
        .filter(Turn.run_id == run.id, Turn.summarized == False)  # noqa: E712
        .order_by(Turn.id.desc())
        .limit(CONTEXT_RECENT_TURNS)
        .all()
    )[::-1]

    try:
        result = master.run_turn(run.state, run.summary or "", recent, body.text.strip(),
                                 dungeon_id=run.dungeon or DEFAULT_DUNGEON)
    except Exception:
        import traceback
        traceback.print_exc()  # причина сбоя — в консоль Replit
        # вернуть списанный ход и ответить по-человечески
        user.turns_today = max(0, user.turns_today - 1)
        db.commit()
        raise HTTPException(502, "Мастер подземелья на миг потерял нить — сбой связи. Ход не списан, повтори.")
    return _apply_gm_result(db, run, body.text.strip(), result)


@router.get("/classes_meta")
def classes_meta():
    return {"classes": {k: {"name": v["name"], "desc": v["desc"]} for k, v in rules.CLASSES.items()}}


class LevelupIn(BaseModel):
    stat: str


@router.post("/run/{run_id}/levelup")
def spend_stat(run_id: int, body: LevelupIn, tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    user = _get_or_create_user(db, tg)
    run = db.query(Run).filter(Run.id == run_id, Run.user_id == user.id, Run.status == "active").first()
    if not run:
        raise HTTPException(404, "Активный забег не найден")
    st = copy.deepcopy(run.state)
    if int(st.get("stat_points", 0)) <= 0:
        raise HTTPException(409, "Нет свободных очков характеристик")
    if body.stat not in rules.STATS:
        raise HTTPException(422, "Нет такой характеристики")
    if int(st["stats"].get(body.stat, 10)) >= 20:
        raise HTTPException(409, "Характеристика на пределе смертного (20)")
    st["stats"][body.stat] = int(st["stats"].get(body.stat, 10)) + 1
    st["stat_points"] = int(st["stat_points"]) - 1
    run.state = st
    db.commit()
    return {"state": run.state}


class TalentIn(BaseModel):
    talent_id: str


@router.post("/run/{run_id}/talent")
def pick_talent(run_id: int, body: TalentIn, tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    from ..game.talents import TALENTS, capacity_bonus
    user = _get_or_create_user(db, tg)
    run = db.query(Run).filter(Run.id == run_id, Run.user_id == user.id, Run.status == "active").first()
    if not run:
        raise HTTPException(404, "Активный забег не найден")
    st = copy.deepcopy(run.state)
    if int(st.get("talent_points", 0)) <= 0:
        raise HTTPException(409, "Выбор таланта пока не заслужен")
    if body.talent_id not in TALENTS:
        raise HTTPException(422, "Нет такого таланта")
    if body.talent_id in (st.get("talents") or []):
        raise HTTPException(409, "Этот талант уже освоен")
    st["talents"] = list(st.get("talents") or []) + [body.talent_id]
    st["talent_points"] = int(st["talent_points"]) - 1
    if TALENTS[body.talent_id]["kind"] == "capacity_bonus":
        st["backpack"]["capacity"] = int(st["backpack"]["capacity"]) + TALENTS[body.talent_id]["bonus"]
    run.state = st
    db.commit()
    return {"state": run.state}


@router.post("/run/{run_id}/abandon")
def abandon(run_id: int, tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    user = _get_or_create_user(db, tg)
    run = db.query(Run).filter(Run.id == run_id, Run.user_id == user.id).first()
    if not run or run.status != "active":
        raise HTTPException(404, "Активный забег не найден")
    run.status = "abandoned"
    user.total_runs += 1
    _finish_seeker(db, run, died=True, final_state=run.state)  # бросить забег = бросить искателя тьме
    db.commit()
    return {"ok": True}
