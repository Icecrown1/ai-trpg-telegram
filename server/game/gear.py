"""Снаряжение: слоты, характеристики, кузнечный каталог. Все бонусы применяет сервер.

Вещь — словарь: name, slot, atk (к попаданию), dmg (кубик урона), def (к защите), dur (прочность),
value (цена в золоте), props (особое свойство словами), two_handed (держит обе руки).
Надетое лежит в слотах equipment, запасное — в сумке bag. Погиб искатель — сгинуло всё.
"""
import re
import secrets

SLOTS = {"weapon": "Оружие", "offhand": "Левая рука", "head": "Голова", "armor": "Тело", "pack": "Рюкзак"}
WEAR_SLOTS = ("weapon", "offhand", "head", "armor")
BAG_LIMIT = 6

GEAR = {
    # --- броня ---
    "leather_armor": {"name": "Кожаный доспех", "slot": "armor", "def": 1, "dur": 3, "value": 20,
                      "forge": 1, "cost": {"leather": 3, "cloth": 1}, "gold": 20},
    "iron_mail":     {"name": "Железная кольчуга", "slot": "armor", "def": 2, "dur": 4, "value": 60,
                      "forge": 2, "cost": {"iron_ingot": 3, "leather": 2}, "gold": 60},
    "mithril_plate": {"name": "Мифриловый панцирь", "slot": "armor", "def": 3, "dur": 5, "value": 200,
                      "forge": 3, "cost": {"mithril": 3, "iron_ingot": 2}, "gold": 200},
    # --- голова и левая рука ---
    "iron_helm":     {"name": "Железный шлем", "slot": "head", "def": 1, "dur": 4, "value": 25,
                      "forge": 1, "cost": {"iron_ingot": 2, "leather": 1}, "gold": 25},
    "bound_shield":  {"name": "Окованный щит", "slot": "offhand", "def": 1, "dur": 4, "value": 20,
                      "forge": 1, "cost": {"wood": 3, "iron_ingot": 1}, "gold": 20},
    # --- оружие ---
    "iron_sword":    {"name": "Железный меч", "slot": "weapon", "atk": 1, "dmg": "1d8", "dur": 4, "value": 40,
                      "forge": 1, "cost": {"iron_ingot": 2, "wood": 1}, "gold": 40},
    "steel_axe":     {"name": "Калёный топор", "slot": "weapon", "atk": 1, "dmg": "1d8+1", "dur": 5, "value": 90,
                      "forge": 2, "cost": {"iron_ingot": 3, "wood_hard": 2}, "gold": 90},
    "mithril_blade": {"name": "Мифриловый клинок", "slot": "weapon", "atk": 2, "dmg": "1d8+1d4", "dur": 6,
                      "value": 250, "forge": 3, "cost": {"mithril": 2, "ash_essence": 1}, "gold": 250},
    # --- рюкзаки: 12 → 16 → 20 → 24 слота ---
    "reinforced_pack": {"name": "Укреплённый рюкзак", "slot": "pack", "capacity": 4, "value": 30,
                        "forge": 1, "cost": {"leather": 4, "iron_ingot": 1}, "gold": 50},
    "travel_pack":     {"name": "Дорожный ранец", "slot": "pack", "capacity": 8, "value": 80,
                        "forge": 2, "cost": {"leather": 6, "cloth": 4, "iron_ingot": 2}, "gold": 90},
    "dwarf_pack":      {"name": "Дварфийский короб", "slot": "pack", "capacity": 12, "value": 180,
                        "forge": 3, "cost": {"wood_hard": 4, "iron_ingot": 4, "leather": 4}, "gold": 200},
}

# стартовые вещи классов: по имени из списка start_items
STARTER_GEAR = {
    "Меч":                  {"slot": "weapon", "atk": 0, "dmg": "1d8", "dur": 3, "value": 10},
    "Посох":                {"slot": "weapon", "atk": 0, "dmg": "1d6", "dur": 3, "value": 3,
                             "props": "фокус заклинаний", "two_handed": True},
    "Булава":               {"slot": "weapon", "atk": 0, "dmg": "1d6", "dur": 4, "value": 8,
                             "props": "дробящее: хорошо против скелетов и брони"},
    "Кинжал":               {"slot": "weapon", "atk": 0, "dmg": "1d4", "dur": 3, "value": 5,
                             "props": "лёгкий: удар из тени, можно метнуть"},
    "Короткий лук":         {"slot": "weapon", "atk": 0, "dmg": "1d6", "dur": 3, "value": 12,
                             "props": "стрелковое: бьёт издалека", "two_handed": True},
    "Двуручный меч":        {"slot": "weapon", "atk": 0, "dmg": "2d6", "dur": 4, "value": 20, "two_handed": True},
    "Посох из живого дуба": {"slot": "weapon", "atk": 0, "dmg": "1d6", "dur": 4, "value": 6,
                             "props": "фокус друида", "two_handed": True},
    "Охотничий нож":        {"slot": "weapon", "atk": 0, "dmg": "1d4", "dur": 3, "value": 3,
                             "props": "разделка туш, запасной клинок"},
    "Кольчуга":             {"slot": "armor", "def": 1, "dur": 4, "value": 15},
    "Латный нагрудник":     {"slot": "armor", "def": 2, "dur": 4, "value": 25},
    "Щит":                  {"slot": "offhand", "def": 1, "dur": 4, "value": 8},
}

# находки мастера, записанные словами в inventory_add: опознаём как снаряжение
_GENERIC = [
    (r"двуручн\w* (меч|топор|молот)", {"slot": "weapon", "dmg": "2d6", "two_handed": True, "value": 18}),
    (r"\bлук\b|арбалет", {"slot": "weapon", "dmg": "1d6", "two_handed": True, "value": 12,
                          "props": "стрелковое"}),
    (r"\bмеч\b|сабл|палаш", {"slot": "weapon", "dmg": "1d8", "value": 10}),
    (r"топор|секир", {"slot": "weapon", "dmg": "1d8", "value": 9}),
    (r"булав|молот|кистен|палиц", {"slot": "weapon", "dmg": "1d6", "value": 7, "props": "дробящее"}),
    (r"кинжал|\bнож\b|стилет", {"slot": "weapon", "dmg": "1d4", "value": 4, "props": "лёгкий"}),
    (r"копь[её]|рогатин", {"slot": "weapon", "dmg": "1d8", "value": 8, "two_handed": True}),
    (r"шлем|шапел|капюшон с кольчуж", {"slot": "head", "def": 1, "value": 10}),
    (r"\bщит\b", {"slot": "offhand", "def": 1, "value": 8}),
    (r"латы|нагрудник|панцир|кираса", {"slot": "armor", "def": 2, "value": 25}),
    (r"кольчуг", {"slot": "armor", "def": 2, "value": 20}),
    (r"доспех|куртк\w* из кож|стёган|стеган|бригантин", {"slot": "armor", "def": 1, "value": 12}),
]
_NOT_GEAR = re.compile(r"ключ|свиток|зель|отмычк|верёвк|веревк|карт[аы]\b|ножн|рукоять|обломок|сломан|точил", re.I)
_DICE = re.compile(r"^\d?d(4|6|8|10|12)([+-]\d)?(\+\d?d(4|6|8))?$")


def _uid() -> str:
    return secrets.token_hex(3)


def make_item(name: str, base: dict) -> dict:
    it = {"uid": _uid(), "name": str(name)[:40], "slot": base["slot"]}
    for k in ("atk", "dmg", "def", "dur", "value", "props", "two_handed", "capacity"):
        if base.get(k) not in (None, "", False):
            it[k] = base[k]
    return it


def craft_item(gid: str) -> dict:
    return make_item(GEAR[gid]["name"], GEAR[gid])


def gear_from_name(name: str):
    """Строка инвентаря → вещь, если это узнаваемое снаряжение; иначе None."""
    if not isinstance(name, str):
        return None
    if name in STARTER_GEAR:
        return make_item(name, STARTER_GEAR[name])
    low = name.lower()
    if _NOT_GEAR.search(low):
        return None
    for pat, base in _GENERIC:
        if re.search(pat, low):
            return make_item(name, base)
    return None


def sanitize_gear(raw, depth: int = 1):
    """Вещь из state_delta.gear_add: чистим поля и режем силу по глубине находки."""
    if isinstance(raw, str):
        return gear_from_name(raw)
    if not isinstance(raw, dict) or not str(raw.get("name") or "").strip():
        return None
    slot = raw.get("slot")
    if slot not in WEAR_SLOTS:
        return gear_from_name(str(raw["name"]))
    depth = max(1, int(depth or 1))
    cap = 1 + depth // 2              # глубина 1 — до +1, 2-3 — до +2, 4+ — до +3
    cap = min(cap, 3)
    base = {"slot": slot}
    try:
        if slot == "weapon":
            base["atk"] = max(0, min(cap, int(raw.get("atk") or 0)))
            dmg = str(raw.get("dmg") or "1d6").replace(" ", "")
            base["dmg"] = dmg if _DICE.match(dmg) else "1d6"
            base["two_handed"] = bool(raw.get("two_handed"))
        else:
            base["def"] = max(0, min(cap, int(raw.get("def") or 1)))
        base["dur"] = max(1, min(6, int(raw.get("dur") or 3)))
        base["value"] = max(1, min(60 * depth, int(raw.get("value") or 5 * depth)))
    except (TypeError, ValueError):
        return gear_from_name(str(raw["name"]))
    if raw.get("props"):
        base["props"] = str(raw["props"])[:80]
    return make_item(str(raw["name"]).strip(), base)


def fill_item(it: dict) -> dict:
    """Старые вещи (до системы слотов) — дописываем недостающие поля из каталога."""
    if not isinstance(it, dict):
        return it
    it = dict(it)
    src = GEAR.get(it.get("id")) or STARTER_GEAR.get(it.get("name")) or {}
    for k in ("value", "props", "two_handed", "dmg", "atk", "def", "dur", "capacity"):
        if k not in it and src.get(k) not in (None, "", False):
            it[k] = src[k]
    if "slot" not in it and src.get("slot"):
        it["slot"] = src["slot"]
    it.setdefault("uid", _uid())
    return it


def normalize_loadout(equipment: dict, bag: list, inventory: list):
    """Разложить вещи по местам: стартовое снаряжение из инвентаря — в слоты или сумку.
    Возвращает (equipment, bag, inventory)."""
    eq = {k: fill_item(v) for k, v in (equipment or {}).items() if v}
    bag = [fill_item(b) for b in (bag or []) if isinstance(b, dict)]
    inv = []
    for name in inventory or []:
        it = make_item(name, STARTER_GEAR[name]) if isinstance(name, str) and name in STARTER_GEAR else None
        if not it:
            inv.append(name)
            continue
        slot = it["slot"]
        if slot == "offhand" and (eq.get("weapon") or {}).get("two_handed"):
            bag.append(it)
        elif not eq.get(slot):
            eq[slot] = it
        else:
            bag.append(it)
    return eq, bag[:BAG_LIMIT + 4], inv


class GearError(Exception):
    pass


def equip(eq: dict, bag: list, uid: str):
    """Надеть вещь из сумки; занятое место уезжает в сумку. Двуручное держит обе руки."""
    it = next((b for b in bag if b.get("uid") == uid), None)
    if not it:
        raise GearError("Этой вещи нет в сумке")
    slot = it.get("slot")
    if slot not in WEAR_SLOTS:
        raise GearError("Это не надевается")
    if slot == "offhand" and (eq.get("weapon") or {}).get("two_handed"):
        raise GearError("Двуручное оружие держит обе руки — сначала смени оружие")
    bag.remove(it)
    if eq.get(slot):
        bag.append(eq[slot])
    eq[slot] = it
    if slot == "weapon" and it.get("two_handed") and eq.get("offhand"):
        bag.append(eq.pop("offhand"))
    return eq, bag


def unequip(eq: dict, bag: list, slot: str):
    if slot not in WEAR_SLOTS or not eq.get(slot):
        raise GearError("В этом месте ничего нет")
    if len(bag) >= BAG_LIMIT:
        raise GearError(f"Сумка полна ({BAG_LIMIT} вещей)")
    bag.append(eq.pop(slot))
    return eq, bag


def defense(state: dict) -> int:
    """Защита игрока: 10 + мод ЛОВ + тело + голова + левая рука. Единственный источник истины."""
    dex = int((state.get("stats") or {}).get("DEX", 10))
    eq = state.get("equipment") or {}
    worn = sum(int((eq.get(s) or {}).get("def", 0) or 0) for s in ("armor", "head", "offhand"))
    stoneskin = 2 if int((state.get("flags") or {}).get("stone_skin", 0) or 0) > 0 else 0
    from .talents import defense_bonus
    return 10 + (dex - 10) // 2 + worn + stoneskin + defense_bonus(state.get("talents"))


def describe(it: dict) -> str:
    """Короткая строка характеристик для мастера и UI."""
    if not it:
        return ""
    parts = []
    if it.get("dmg"):
        parts.append(f"урон {it['dmg']}" + (f", к попаданию +{it['atk']}" if it.get("atk") else ""))
    if it.get("def"):
        parts.append(f"защита +{it['def']}")
    if it.get("capacity"):
        parts.append(f"рюкзак +{it['capacity']}")
    if it.get("two_handed"):
        parts.append("двуручное")
    if it.get("props"):
        parts.append(it["props"])
    if it.get("value"):
        parts.append(f"цена {it['value']} зол.")
    return ", ".join(parts)
