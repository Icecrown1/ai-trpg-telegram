"""Каталог крафта кузницы. Все бонусы применяет сервер."""

GEAR = {
    # --- броня: def повышает защиту (СЛ вражеских атак), dur — прочность ---
    "leather_armor": {"name": "Кожаный доспех", "slot": "armor", "def": 1, "dur": 3,
                      "forge": 1, "cost": {"leather": 3, "cloth": 1}, "gold": 20},
    "iron_mail":     {"name": "Железная кольчуга", "slot": "armor", "def": 2, "dur": 4,
                      "forge": 2, "cost": {"iron": 4, "leather": 2}, "gold": 60},
    "mithril_plate": {"name": "Мифриловый панцирь", "slot": "armor", "def": 3, "dur": 5,
                      "forge": 3, "cost": {"mithril": 3, "iron": 2}, "gold": 200},
    # --- оружие: atk к броску атаки игрока, dmg — кубик урона для мастера ---
    "iron_sword":    {"name": "Железный меч", "slot": "weapon", "atk": 1, "dmg": "1d8", "dur": 4,
                      "forge": 1, "cost": {"iron": 3, "wood": 1}, "gold": 40},
    "steel_axe":     {"name": "Калёный топор", "slot": "weapon", "atk": 1, "dmg": "1d8+1", "dur": 5,
                      "forge": 2, "cost": {"iron": 5, "wood_hard": 2}, "gold": 90},
    "mithril_blade": {"name": "Мифриловый клинок", "slot": "weapon", "atk": 2, "dmg": "1d8+1d4", "dur": 6,
                      "forge": 3, "cost": {"mithril": 2, "ash_essence": 1}, "gold": 250},
    # --- рюкзак ---
    "reinforced_pack": {"name": "Укреплённый рюкзак", "slot": "pack", "capacity": 4,
                        "forge": 1, "cost": {"leather": 4, "iron": 1}, "gold": 50},
}


def defense(state: dict) -> int:
    """Защита игрока: 10 + мод ЛОВ + броня. Единственный источник истины."""
    dex = int((state.get("stats") or {}).get("DEX", 10))
    armor = ((state.get("equipment") or {}).get("armor") or {})
    stoneskin = 2 if int((state.get("flags") or {}).get("stone_skin", 0) or 0) > 0 else 0
    return 10 + (dex - 10) // 2 + int(armor.get("def", 0)) + stoneskin
