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
from ..game.gear import GEAR, SLOTS as GEAR_SLOTS
from ..game.magic import MAGIC
from ..game.resources import RESOURCES, res_brief, RECIPES, cost_list
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
    from sqlalchemy.exc import IntegrityError
    city = db.query(City).filter(City.user_id == user.id).first()
    if not city:
        city = City(user_id=user.id, buildings=dict(DEFAULT_BUILDINGS),
                    resources={}, gold=0, companions=[], flags={})
        db.add(city)
        try:
            db.commit()
            db.refresh(city)
        except IntegrityError:
            # гонка первого входа: параллельный запрос успел создать город — берём его
            db.rollback()
            city = db.query(City).filter(City.user_id == user.id).first()
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


def _seeker_view(s: Seeker) -> dict:
    """Искатель для экрана города: снаряжение по слотам, сумка, мелочь в инвентаре."""
    from ..game.gear import normalize_loadout, describe, defense
    eq, bag, inv = normalize_loadout(s.equipment or {}, s.gear_bag or [], s.inventory or [])
    return {"id": s.id, "name": s.name, "race": s.race, "cls": s.cls,
            "cls_name": rules.CLASSES[s.cls]["name"], "level": s.level,
            "max_hp": s.max_hp, "runs_survived": s.runs_survived, "status": s.status,
            "equipment": eq, "bag": bag, "inventory": inv,
            "equipment_desc": {k: describe(v) for k, v in eq.items()},
            "bag_desc": [describe(b) for b in bag],
            "defense": defense({"stats": s.stats or {}, "equipment": eq, "talents": s.talents or []})}


def _persist_loadout(s: Seeker):
    """Один раз раскладываем старый инвентарь по слотам — дальше работаем со структурой."""
    from ..game.gear import normalize_loadout
    eq, bag, inv = normalize_loadout(s.equipment or {}, s.gear_bag or [], s.inventory or [])
    s.equipment, s.gear_bag, s.inventory = eq, bag, inv


def city_payload(db: Session, city: City, user: User) -> dict:
    seekers = (
        db.query(Seeker)
        .filter(Seeker.user_id == user.id, Seeker.status != "dead")
        .order_by(Seeker.id)
        .all()
    )
    changed = False
    for sk in seekers:  # старые искатели: стартовые вещи из инвентаря — в слоты, uid — навсегда
        if sk.status == "idle":
            before = (sk.equipment, sk.gear_bag, sk.inventory)
            _persist_loadout(sk)
            changed = changed or before != (sk.equipment, sk.gear_bag, sk.inventory)
    if changed:
        db.commit()
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
        cl = cost_list(nxt.get("cost", {}), city.resources or {}, nxt.get("gold", 0), city.gold or 0)
        upgrades[bid] = {
            "level": cur + 1, "gold": nxt.get("gold", 0),
            "cost": nxt.get("cost", {}),
            "cost_named": res_brief(nxt.get("cost", {})),
            "cost_list": cl, "affordable": all(c["ok"] for c in cl),
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
         "cost_list": cost_list(m["cost"], city.resources or {}, m["gold"], city.gold or 0),
         "available": tower_lvl >= m["tower"]}
        for mid, m in MAGIC.items()
    ] if tower_lvl > 0 else []

    forge_lvl = (city.buildings or {}).get("forge", 0)
    craftable = [
        {"id": gid, "name": g["name"], "slot": g["slot"], "forge": g["forge"],
         "cost": g["cost"], "cost_named": res_brief(g["cost"]), "gold": g["gold"],
         "def": g.get("def"), "atk": g.get("atk"), "dmg": g.get("dmg"),
         "capacity": g.get("capacity"), "dur": g.get("dur"), "value": g.get("value"),
         "cost_list": cost_list(g["cost"], city.resources or {}, g["gold"], city.gold or 0),
         "available": forge_lvl >= g["forge"]}
        for gid, g in GEAR.items()
    ] if forge_lvl > 0 else []
    recipes = [
        {"id": rid, "out": r["out"], "out_name": RESOURCES[r["out"]]["name"], "who": r["who"],
         "building": r["building"], "building_name": BUILDING_DEFS[r["building"]]["name"], "level": r["level"],
         "cost_list": cost_list(r["in"], city.resources or {}, r["gold"], city.gold or 0),
         "available": (city.buildings or {}).get(r["building"], 0) >= r["level"]}
        for rid, r in RECIPES.items()
        if (city.buildings or {}).get(r["building"], 0) >= 1
    ]
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
        "seekers": [_seeker_view(s) for s in seekers],
        "recipes": recipes,
        "chest": list(city.chest or []),
        "gear_slots": {k: v for k, v in GEAR_SLOTS.items()},
        "seeker_slots": seeker_slots(city.buildings),
        "flags": city.flags or {},
    }


@router.get("")
def get_city(tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.tg_id == tg["id"]).first()
    if not user:
        from sqlalchemy.exc import IntegrityError
        user = User(tg_id=tg["id"], username=tg.get("username"), first_name=tg.get("first_name"))
        db.add(user)
        try:
            db.commit()
            db.refresh(user)
        except IntegrityError:
            db.rollback()
            user = db.query(User).filter(User.tg_id == tg["id"]).first()
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
    from ..game.gear import craft_item
    item = {**craft_item(body.item_id), "id": body.item_id}
    eq = dict(seeker.equipment or {})
    if g["slot"] == "pack" or not eq.get(g["slot"]):
        eq[g["slot"]] = item
    else:
        seeker.gear_bag = list(seeker.gear_bag or []) + [item]  # надетое не снимаем — новое в сумку
    seeker.equipment = eq
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
        from sqlalchemy.exc import IntegrityError
        user = User(tg_id=tg["id"], username=tg.get("username"), first_name=tg.get("first_name"))
        db.add(user)
        try:
            db.commit()
            db.refresh(user)
        except IntegrityError:
            db.rollback()
            user = db.query(User).filter(User.tg_id == tg["id"]).first()
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


class RefineIn(BaseModel):
    recipe_id: str
    times: int = 1


@router.post("/refine")
def refine(body: RefineIn, tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    """Переработка сырья в крафтовые материалы в здании нужного уровня."""
    user = db.query(User).filter(User.tg_id == tg["id"]).first()
    if not user:
        raise HTTPException(404, "Сначала зайди в игру")
    city = get_or_create_city(db, user)
    r = RECIPES.get(body.recipe_id)
    if not r:
        raise HTTPException(422, "Такого не делают")
    if (city.buildings or {}).get(r["building"], 0) < r["level"]:
        raise HTTPException(409, f"Нужно здание «{BUILDING_DEFS[r['building']]['name']}» ур.{r['level']}")
    times = max(1, min(10, int(body.times or 1)))
    cres = dict(city.resources or {})
    for rid, cnt in r["in"].items():
        if cres.get(rid, 0) < cnt * times:
            raise HTTPException(409, f"Не хватает: {RESOURCES[rid]['name']} ({cres.get(rid, 0)}/{cnt * times})")
    if (city.gold or 0) < r["gold"] * times:
        raise HTTPException(409, f"Не хватает золота ({city.gold or 0}/{r['gold'] * times})")
    for rid, cnt in r["in"].items():
        cres[rid] -= cnt * times
        if cres[rid] <= 0:
            del cres[rid]
    cres[r["out"]] = cres.get(r["out"], 0) + times
    city.resources = cres
    city.gold = (city.gold or 0) - r["gold"] * times
    db.commit()
    return city_payload(db, city, user)


class ChestIn(BaseModel):
    seeker_id: int
    action: str              # put | take | equip | unequip
    uid: str | None = None   # вещь-снаряжение (в слоте, сумке или сундуке)
    slot: str | None = None  # слот для put/unequip надетого
    item: str | None = None  # мелочь инвентаря (строка) для put
    index: int | None = None # позиция в сундуке для take мелочи


@router.post("/chest")
def chest(body: ChestIn, tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    """Королевский сундук: снять с искателя вещь и положить на хранение, выдать обратно, переодеть."""
    from ..game import gear as G
    user = db.query(User).filter(User.tg_id == tg["id"]).first()
    if not user:
        raise HTTPException(404, "Сначала зайди в игру")
    city = get_or_create_city(db, user)
    sk = db.query(Seeker).filter(Seeker.id == body.seeker_id, Seeker.user_id == user.id,
                                 Seeker.status == "idle").first()
    if not sk:
        raise HTTPException(404, "Искатель не найден или в подземелье")
    _persist_loadout(sk)
    eq, bag, inv = dict(sk.equipment or {}), list(sk.gear_bag or []), list(sk.inventory or [])
    box = list(city.chest or [])
    try:
        if body.action == "equip":
            src = next((b for b in box if b.get("kind") == "gear" and b.get("uid") == body.uid), None)
            if src:  # прямо из сундука на героя: временно в сумку, оттуда в слот
                box.remove(src)
                it = {k: v for k, v in src.items() if k != "kind"}
                bag.append(it)
            G.equip(eq, bag, body.uid)
            while len(bag) > G.BAG_LIMIT:  # снятое не влезло в сумку — уходит в сундук
                box.append({"kind": "gear", **bag.pop()})
        elif body.action == "unequip":
            G.unequip(eq, bag, body.slot)
        elif body.action == "put":
            if body.slot:
                if body.slot not in eq or not eq.get(body.slot):
                    raise G.GearError("В этом месте ничего нет")
                box.append({"kind": "gear", **eq.pop(body.slot)})
            elif body.uid:
                it = next((b for b in bag if b.get("uid") == body.uid), None)
                if not it:
                    raise G.GearError("Этой вещи нет в сумке")
                bag.remove(it)
                box.append({"kind": "gear", **it})
            elif body.item:
                if body.item not in inv:
                    raise G.GearError("Этого нет при искателе")
                inv.remove(body.item)
                box.append({"kind": "item", "name": body.item})
            else:
                raise G.GearError("Что положить?")
        elif body.action == "take":
            if body.uid:
                it = next((b for b in box if b.get("kind") == "gear" and b.get("uid") == body.uid), None)
                if not it:
                    raise G.GearError("В сундуке такого нет")
                if len(bag) >= G.BAG_LIMIT:
                    raise G.GearError(f"Сумка полна ({G.BAG_LIMIT} вещей)")
                box.remove(it)
                bag.append({k: v for k, v in it.items() if k != "kind"})
            elif body.index is not None and 0 <= body.index < len(box) and box[body.index].get("kind") == "item":
                if len(inv) >= 16:
                    raise G.GearError("Руки заняты — больше не унести")
                inv.append(box.pop(body.index)["name"])
            else:
                raise G.GearError("В сундуке такого нет")
        else:
            raise G.GearError("Неизвестное действие")
    except G.GearError as e:
        raise HTTPException(409, str(e))
    if len(box) > 60:
        raise HTTPException(409, "Сундук полон (60 вещей)")
    sk.equipment, sk.gear_bag, sk.inventory = eq, bag, inv
    city.chest = box
    db.commit()
    return city_payload(db, city, user)
