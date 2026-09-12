from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User, Run, Turn, City
from ..telegram_auth import get_tg_user
from ..config import FREE_TURNS_PER_DAY, CONTEXT_RECENT_TURNS, SUMMARIZE_EVERY
from ..game import rules, state as state_mod, master

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


DEFAULT_BUILDINGS = {"tavern": 1, "forge": 0, "mage_tower": 0, "throne": 0}


def _get_or_create_city(db: Session, user: User) -> City:
    city = db.query(City).filter(City.user_id == user.id).first()
    if not city:
        city = City(user_id=user.id, buildings=dict(DEFAULT_BUILDINGS), resources={}, gold=0)
        db.add(city)
        db.commit()
        db.refresh(city)
    return city


def _city_payload(city: City) -> dict:
    from ..game.resources import res_brief
    return {"buildings": city.buildings, "gold": city.gold,
            "resources": city.resources, "resources_named": res_brief(city.resources)}


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
        "status": run.status,
        "death_cause": run.death_cause,
        "state": run.state,
        "turn_count": run.turn_count,
        "last": last,
    }


def _apply_gm_result(db: Session, run: Run, player_input: str, result: dict) -> dict:
    new_state = state_mod.apply_delta(dict(run.state), result.get("state_delta") or {})
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

    _ART_TAGS = {"gates","stairs","skull","goblin","rat","undead","cultist","merchant",
                 "chest","altar","potion","well","torch","boss"}
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

    if game_over:
        run.status = "dead"
        run.death_cause = result.get("death_cause") or "Погиб в глубинах Кар-Морда"
        user = run.user
        user.total_runs += 1
        user.deepest_level = max(user.deepest_level, new_state.get("depth", 1))
        user.best_gold = max(user.best_gold, new_state.get("gold", 0))

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
    name: str = Field(min_length=1, max_length=24)
    race: str
    cls: str = Field(alias="class")

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

    try:
        char = rules.new_character(body.name, body.race, body.cls)
    except ValueError:
        raise HTTPException(422, "Неизвестная раса или класс")

    run = Run(user_id=user.id, state=char)
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        result = master.opening_scene(char)
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
        result = master.run_turn(run.state, run.summary or "", recent, body.text.strip())
    except Exception:
        import traceback
        traceback.print_exc()  # причина сбоя — в консоль Replit
        # вернуть списанный ход и ответить по-человечески
        user.turns_today = max(0, user.turns_today - 1)
        db.commit()
        raise HTTPException(502, "Мастер подземелья на миг потерял нить — сбой связи. Ход не списан, повтори.")
    return _apply_gm_result(db, run, body.text.strip(), result)


@router.post("/run/{run_id}/abandon")
def abandon(run_id: int, tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    user = _get_or_create_user(db, tg)
    run = db.query(Run).filter(Run.id == run_id, Run.user_id == user.id).first()
    if not run or run.status != "active":
        raise HTTPException(404, "Активный забег не найден")
    run.status = "abandoned"
    user.total_runs += 1
    db.commit()
    return {"ok": True}
