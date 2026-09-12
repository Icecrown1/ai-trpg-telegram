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
from ..game.resources import RESOURCES, res_brief
from ..game import rules

router = APIRouter(prefix="/api/city", tags=["city"])

DEFAULT_BUILDINGS = {"tavern": 1, "forge": 0, "mage_tower": 0, "throne": 0}

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
    forge_lvl = (city.buildings or {}).get("forge", 0)
    craftable = [
        {"id": gid, "name": g["name"], "slot": g["slot"], "forge": g["forge"],
         "cost": g["cost"], "cost_named": res_brief(g["cost"]), "gold": g["gold"],
         "def": g.get("def"), "atk": g.get("atk"), "dmg": g.get("dmg"),
         "capacity": g.get("capacity"), "dur": g.get("dur"),
         "available": forge_lvl >= g["forge"]}
        for gid, g in GEAR.items()
    ] if forge_lvl > 0 else []
    return {
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
