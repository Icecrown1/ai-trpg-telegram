"""Город-замок: здания, склад, таверна, искатели."""
import copy
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User, City, Seeker
from ..telegram_auth import get_tg_user
from ..game.buildings import BUILDING_DEFS, seeker_slots, companion_slots
from ..game.gear import GEAR
from ..game.magic import MAGIC
from ..game.resources import RESOURCES, res_brief
from ..game import rules

router = APIRouter(prefix="/api/city", tags=["city"])

DEFAULT_BUILDINGS = {"tavern": 0, "forge": 0, "mage_tower": 0, "throne": 0}

# лица, которые могут сидеть в таверне (генерируются детерминированно от city.id + total_runs)
_PATRON_POOL = [
    {"name": "Борин", "cls": "fighter", "price": 25, "bio": "Ветеран трёх обвалов. Пьёт молча, бьёт громко."},
    {"name": "Тисса", "cls": "rogue", "price": 30, "bio": "Улыбается так, что стоит проверить карманы."},
    {"name": "Олаф", "cls": "archer", "price": 25, "bio": "Хвастает, что попадает в глаз крысе в темноте."},
    {"name": "Мирна", "cls": "cleric", "price": 35, "bio": "Ушла из монастыря. Не спрашивай почему."},
    {"name": "Гримм", "cls": "templar", "price": 45, "bio": "Обет молчания кончился. Теперь не заткнуть."},
    {"name": "Ива", "cls": "druid", "price": 40, "bio": "От неё пахнет лесом, которого здесь нет."},
]


def get_or_create_city(db: Session, user: User) -> City:
    city = db.query(City).filter(City.user_id == user.id).first()
    if not city:
        city = City(user_id=user.id, buildings=dict(DEFAULT_BUILDINGS),
                    resources={}, gold=0, companions=[], flags={})
        db.add(city)
        db.commit()
        db.refresh(city)
    if city.companions is None:
        city.companions = []
    if city.flags is None:
        city.flags = {}
    return city


def tavern_patrons(city: City, user: User) -> list:
    """Кто сидит в таверне сейчас: 2-3 лица, ротация от числа забегов."""
    seed = (city.id * 7 + (user.total_runs or 0)) % len(_PATRON_POOL)
    count = 2 + (1 if (city.buildings or {}).get("tavern", 1) >= 2 else 0)
    hired = {c.get("name") for c in (city.companions or [])}
    out = []
    i = seed
    while len(out) < count and len(out) < len(_PATRON_POOL):
        p = _PATRON_POOL[i % len(_PATRON_POOL)]
        if p["name"] not in hired:
            out.append(p)
        i += 1
    return out


RUINS = [
    {"id": 1, "name": "Разрушенный дом у колодца", "loot": {"wood": 2, "stone": 1},
     "desc": "Крыша провалилась, но брёвна живые."},
    {"id": 2, "name": "Разрушенный дом с обгоревшей стеной", "loot": {"wood": 1, "stone": 2},
     "desc": "Кладка крепкая — камень пойдёт в дело."},
]


def city_payload(db: Session, city: City, user: User) -> dict:
    seekers = (
        db.query(Seeker)
        .filter(Seeker.user_id == user.id, Seeker.status != "dead")
        .order_by(Seeker.id)
        .all()
    )
    upgrades = {}
    for bid, bdef in BUILDING_DEFS.items():
        cur = (city.buildings or {}).get(bid, 0)
        if bdef.get("locked_by") and not (city.flags or {}).get(bdef["locked_by"]):
            upgrades[bid] = {"locked": True, "text": bdef["locked_text"]}
            continue
        nxt = bdef.get("levels", {}).get(cur + 1)
        if not nxt:
            upgrades[bid] = None
            continue
        if nxt.get("requires_flag") and not (city.flags or {}).get(nxt["requires_flag"]):
            upgrades[bid] = {"locked": True, "text": "Пока недоступно"}
            continue
        upgrades[bid] = {
            "level": cur + 1, "gold": nxt.get("gold", 0),
            "cost": nxt.get("cost", {}),
            "cost_named": res_brief(nxt.get("cost", {})),
            "desc": nxt.get("desc", ""),
        }
    from datetime import datetime, timedelta, date
    from ..config import RUNS_PER_WINDOW, RUN_WINDOW_HOURS
    window_h = max(2, RUN_WINDOW_HOURS - int((city.buildings or {}).get("throne", 0)))
    now = datetime.utcnow()
    stamps = [s for s in (user.run_stamps or [])
              if now - datetime.fromisoformat(s) < timedelta(hours=window_h)]
    runs_left = max(0, RUNS_PER_WINDOW - len(stamps))
    next_in = None
    if runs_left == 0 and stamps:
        oldest = min(datetime.fromisoformat(s) for s in stamps)
        wait = oldest + timedelta(hours=window_h) - now
        next_in = f"{int(wait.total_seconds() // 3600)}ч {int(wait.total_seconds() % 3600 // 60):02d}м"

    daily = None
    throne_lvl = (city.buildings or {}).get("throne", 0)
    if throne_lvl >= 1:
        pool = [("stone", 4), ("wood", 4), ("leather", 3), ("iron", 2), ("bone", 2), ("cloth", 3)]
        today = date.today()
        rid_, cnt_ = pool[(today.toordinal() + city.id) % len(pool)]
        daily = {
            "res": rid_, "res_name": RESOURCES[rid_]["name"], "count": cnt_,
            "reward_gold": 30 + 20 * throne_lvl,
            "done": (city.flags or {}).get("daily_done") == today.isoformat(),
            "can_claim": (city.resources or {}).get(rid_, 0) >= cnt_,
        }

    tower_lvl = (city.buildings or {}).get("mage_tower", 0)
    enchantable = [
        {"id": mid, "name": m["name"], "tower": m["tower"], "effect": m["effect"],
         "cost": m["cost"], "cost_named": res_brief(m["cost"]), "gold": m["gold"],
         "available": tower_lvl >= m["tower"]}
        for mid, m in MAGIC.items()
    ] if tower_lvl > 0 else []

    forge_lvl = (city.buildings or {}).get("forge", 0)
    craftable = [
        {"id": gid, "name": g["name"], "slot": g["slot"], "forge": g["forge"],
         "cost": g["cost"], "cost_named": res_brief(g["cost"]), "gold": g["gold"],
         "def": g.get("def"), "atk": g.get("atk"), "dmg": g.get("dmg"),
         "capacity": g.get("capacity"), "dur": g.get("dur"),
         "available": forge_lvl >= g["forge"]}
        for gid, g in GEAR.items()
    ] if forge_lvl > 0 else []
    cleared = set((city.flags or {}).get("ruins_cleared") or [])
    ruins = None
    if not (city.flags or {}).get("prologue_done"):
        ruins = [
            {**r, "loot_named": res_brief(r["loot"]), "cleared": r["id"] in cleared}
            for r in RUINS
        ]
    return {
        "ruins": ruins,
        "runs_left": runs_left, "runs_per_window": RUNS_PER_WINDOW,
        "run_window_hours": window_h, "next_run_in": next_in,
        "daily": daily,
        "enchantable": enchantable,
        "craftable": craftable,
        "buildings": city.buildings,
        "building_names": {k: v["name"] for k, v in BUILDING_DEFS.items()},
        "upgrades": upgrades,
        "gold": city.gold or 0,
        "resources": city.resources or {},
        "resources_named": res_brief(city.resources or {}),
        "companions": city.companions or [],
        "companion_slots": companion_slots(city.buildings),
        "seekers": [
            {"id": s.id, "name": s.name, "race": s.race, "cls": s.cls,
             "cls_name": rules.CLASSES[s.cls]["name"], "level": s.level,
             "max_hp": s.max_hp, "runs_survived": s.runs_survived, "status": s.status,
             "equipment": s.equipment or {}}
            for s in seekers
        ],
        "seeker_slots": seeker_slots(city.buildings),
        "flags": city.flags or {},
    }


@router.get("")
def get_city(tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.tg_id == tg["id"]).first()
    if not user:
        user = User(tg_id=tg["id"], username=tg.get("username"), first_name=tg.get("first_name"))
        db.add(user)
        db.commit()
        db.refresh(user)
    city = get_or_create_city(db, user)
    payload = city_payload(db, city, user)
    payload["tavern_patrons"] = tavern_patrons(city, user)
    return payload


class BuildIn(BaseModel):
    building: str


@router.post("/build")
def build(body: BuildIn, tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.tg_id == tg["id"]).first()
    if not user:
        raise HTTPException(404, "Сначала зайди в игру")
    city = get_or_create_city(db, user)
    bdef = BUILDING_DEFS.get(body.building)
    if not bdef:
        raise HTTPException(422, "Нет такого здания")
    if bdef.get("locked_by") and not (city.flags or {}).get(bdef["locked_by"]):
        raise HTTPException(409, bdef["locked_text"])
    cur = (city.buildings or {}).get(body.building, 0)
    nxt = bdef.get("levels", {}).get(cur + 1)
    if not nxt:
        raise HTTPException(409, "Выше пока не строится")
    if nxt.get("requires_flag") and not (city.flags or {}).get(nxt["requires_flag"]):
        raise HTTPException(409, "Условие улучшения ещё не выполнено")
    cres = dict(city.resources or {})
    for rid, cnt in (nxt.get("cost") or {}).items():
        if cres.get(rid, 0) < cnt:
            raise HTTPException(409, f"Не хватает: {RESOURCES[rid]['name']} ({cres.get(rid, 0)}/{cnt})")
    if (city.gold or 0) < nxt.get("gold", 0):
        raise HTTPException(409, f"Не хватает золота ({city.gold or 0}/{nxt.get('gold', 0)})")
    for rid, cnt in (nxt.get("cost") or {}).items():
        cres[rid] -= cnt
        if cres[rid] <= 0:
            del cres[rid]
    city.resources = cres
    city.gold = (city.gold or 0) - nxt.get("gold", 0)
    city.buildings = {**(city.buildings or {}), body.building: cur + 1}
    db.commit()
    return city_payload(db, city, user)


class HireIn(BaseModel):
    name: str


@router.post("/hire")
def hire(body: HireIn, tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.tg_id == tg["id"]).first()
    if not user:
        raise HTTPException(404, "Сначала зайди в игру")
    city = get_or_create_city(db, user)
    comps = list(city.companions or [])
    if len(comps) >= companion_slots(city.buildings):
        raise HTTPException(409, "Все места соратников заняты. Тронный зал расширит дружину.")
    patron = next((p for p in tavern_patrons(city, user) if p["name"] == body.name), None)
    if not patron:
        raise HTTPException(404, "Этого посетителя сейчас нет в таверне")
    if (city.gold or 0) < patron["price"]:
        raise HTTPException(409, f"Не хватает золота ({city.gold or 0}/{patron['price']})")
    c = rules.CLASSES[patron["cls"]]
    max_hp = c["hit_die"] + 2
    city.gold = (city.gold or 0) - patron["price"]
    comps.append({"name": patron["name"], "cls": patron["cls"], "cls_name": c["name"],
                  "hp": max_hp, "max_hp": max_hp, "loyalty": 0})
    city.companions = comps
    db.commit()
    payload = city_payload(db, city, user)
    payload["tavern_patrons"] = tavern_patrons(city, user)
    return payload


class CraftIn(BaseModel):
    item_id: str
    seeker_id: int


@router.post("/craft")
def craft(body: CraftIn, tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.tg_id == tg["id"]).first()
    if not user:
        raise HTTPException(404, "Сначала зайди в игру")
    city = get_or_create_city(db, user)
    from datetime import datetime, timedelta, date
    from ..config import RUNS_PER_WINDOW, RUN_WINDOW_HOURS
    window_h = max(2, RUN_WINDOW_HOURS - int((city.buildings or {}).get("throne", 0)))
    now = datetime.utcnow()
    stamps = [s for s in (user.run_stamps or [])
              if now - datetime.fromisoformat(s) < timedelta(hours=window_h)]
    runs_left = max(0, RUNS_PER_WINDOW - len(stamps))
    next_in = None
    if runs_left == 0 and stamps:
        oldest = min(datetime.fromisoformat(s) for s in stamps)
        wait = oldest + timedelta(hours=window_h) - now
        next_in = f"{int(wait.total_seconds() // 3600)}ч {int(wait.total_seconds() % 3600 // 60):02d}м"

    daily = None
    throne_lvl = (city.buildings or {}).get("throne", 0)
    if throne_lvl >= 1:
        pool = [("stone", 4), ("wood", 4), ("leather", 3), ("iron", 2), ("bone", 2), ("cloth", 3)]
        today = date.today()
        rid_, cnt_ = pool[(today.toordinal() + city.id) % len(pool)]
        daily = {
            "res": rid_, "res_name": RESOURCES[rid_]["name"], "count": cnt_,
            "reward_gold": 30 + 20 * throne_lvl,
            "done": (city.flags or {}).get("daily_done") == today.isoformat(),
            "can_claim": (city.resources or {}).get(rid_, 0) >= cnt_,
        }

    tower_lvl = (city.buildings or {}).get("mage_tower", 0)
    enchantable = [
        {"id": mid, "name": m["name"], "tower": m["tower"], "effect": m["effect"],
         "cost": m["cost"], "cost_named": res_brief(m["cost"]), "gold": m["gold"],
         "available": tower_lvl >= m["tower"]}
        for mid, m in MAGIC.items()
    ] if tower_lvl > 0 else []

    forge_lvl = (city.buildings or {}).get("forge", 0)
    g = GEAR.get(body.item_id)
    if not g:
        raise HTTPException(422, "Торин такого не куёт")
    if forge_lvl < g["forge"]:
        raise HTTPException(409, f"Нужна кузница уровня {g['forge']}")
    seeker = db.query(Seeker).filter(
        Seeker.id == body.seeker_id, Seeker.user_id == user.id, Seeker.status == "idle"
    ).first()
    if not seeker:
        raise HTTPException(404, "Искатель не найден или в подземелье")
    cres = dict(city.resources or {})
    for rid, cnt in g["cost"].items():
        if cres.get(rid, 0) < cnt:
            raise HTTPException(409, f"Не хватает: {RESOURCES[rid]['name']} ({cres.get(rid, 0)}/{cnt})")
    if (city.gold or 0) < g["gold"]:
        raise HTTPException(409, f"Не хватает золота ({city.gold or 0}/{g['gold']})")
    for rid, cnt in g["cost"].items():
        cres[rid] -= cnt
        if cres[rid] <= 0:
            del cres[rid]
    city.resources = cres
    city.gold = (city.gold or 0) - g["gold"]
    item = {"id": body.item_id, "name": g["name"]}
    for k in ("def", "atk", "dmg", "dur", "capacity"):
        if g.get(k) is not None:
            item[k] = g[k]
    seeker.equipment = {**(seeker.equipment or {}), g["slot"]: item}
    db.commit()
    return city_payload(db, city, user)


class EnchantIn(BaseModel):
    item_id: str
    seeker_id: int


@router.post("/enchant")
def enchant(body: EnchantIn, tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.tg_id == tg["id"]).first()
    if not user:
        raise HTTPException(404, "Сначала зайди в игру")
    city = get_or_create_city(db, user)
    tower_lvl = (city.buildings or {}).get("mage_tower", 0)
    m = MAGIC.get(body.item_id)
    if not m:
        raise HTTPException(422, "Финеус поднимает бровь: «Такого я не делаю»")
    if tower_lvl < m["tower"]:
        raise HTTPException(409, f"Нужна башня уровня {m['tower']}")
    seeker = db.query(Seeker).filter(
        Seeker.id == body.seeker_id, Seeker.user_id == user.id, Seeker.status == "idle"
    ).first()
    if not seeker:
        raise HTTPException(404, "Искатель не найден или в подземелье")
    cres = dict(city.resources or {})
    for rid, cnt in m["cost"].items():
        if cres.get(rid, 0) < cnt:
            raise HTTPException(409, f"Не хватает: {RESOURCES[rid]['name']} ({cres.get(rid, 0)}/{cnt})")
    if (city.gold or 0) < m["gold"]:
        raise HTTPException(409, f"Не хватает золота ({city.gold or 0}/{m['gold']})")
    for rid, cnt in m["cost"].items():
        cres[rid] -= cnt
        if cres[rid] <= 0:
            del cres[rid]
    city.resources = cres
    city.gold = (city.gold or 0) - m["gold"]
    seeker.inventory = list(seeker.inventory or []) + [m["name"]]
    db.commit()
    return city_payload(db, city, user)


@router.post("/daily_claim")
def daily_claim(tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    from datetime import date
    user = db.query(User).filter(User.tg_id == tg["id"]).first()
    if not user:
        raise HTTPException(404, "Сначала зайди в игру")
    city = get_or_create_city(db, user)
    payload = city_payload(db, city, user)
    daily = payload.get("daily")
    if not daily:
        raise HTTPException(409, "Тронный зал ещё не даёт поручений")
    if daily["done"]:
        raise HTTPException(409, "Сегодняшнее поручение уже сдано")
    if not daily["can_claim"]:
        raise HTTPException(409, f"На складе мало: {daily['res_name']} нужно {daily['count']}")
    cres = dict(city.resources or {})
    cres[daily["res"]] -= daily["count"]
    if cres[daily["res"]] <= 0:
        del cres[daily["res"]]
    city.resources = cres
    city.gold = (city.gold or 0) + daily["reward_gold"]
    city.flags = {**(city.flags or {}), "daily_done": date.today().isoformat()}
    db.commit()
    return city_payload(db, city, user)


@router.post("/prologue_done")
def prologue_done(tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.tg_id == tg["id"]).first()
    if not user:
        user = User(tg_id=tg["id"], username=tg.get("username"), first_name=tg.get("first_name"))
        db.add(user)
        db.commit()
        db.refresh(user)
    city = get_or_create_city(db, user)
    city.flags = {**(city.flags or {}), "prologue_done": True}
    # фолбэк для «пропустить пролог»: город должен остаться играбельным
    if (city.buildings or {}).get("tavern", 0) < 1:
        city.buildings = {**(city.buildings or {}), "tavern": 1}
    db.commit()
    return city_payload(db, city, user)


class DemolishIn(BaseModel):
    ruin_id: int


@router.post("/demolish")
def demolish(body: DemolishIn, tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.tg_id == tg["id"]).first()
    if not user:
        raise HTTPException(404, "Сначала зайди в игру")
    city = get_or_create_city(db, user)
    if (city.flags or {}).get("prologue_done"):
        raise HTTPException(409, "Руины давно разобраны")
    ruin = next((r for r in RUINS if r["id"] == body.ruin_id), None)
    if not ruin:
        raise HTTPException(422, "Такого дома нет")
    cleared = list((city.flags or {}).get("ruins_cleared") or [])
    if body.ruin_id in cleared:
        raise HTTPException(409, "Этот дом уже разобран")
    cres = dict(city.resources or {})
    for rid, cnt in ruin["loot"].items():
        cres[rid] = cres.get(rid, 0) + cnt
    city.resources = cres
    city.flags = {**(city.flags or {}), "ruins_cleared": cleared + [body.ruin_id]}
    db.commit()
    return city_payload(db, city, user)
