"""Character rules in the spirit of PLATO dnd / AD&D. All numbers server-side."""
from ..dice import roll_3d6

STATS = ["STR", "INT", "WIS", "DEX", "CON", "CHA"]

CLASSES = {
    "fighter": {
        "name": "Воин", "hit_die": 10,
        "start_items": ["Меч", "Кольчуга", "Факел"],
        "desc": "Сталь решает всё. Больше HP, точнее удары.",
    },
    "mage": {
        "name": "Маг", "hit_die": 4,
        "start_items": ["Посох", "Гримуар", "Свеча"],
        "desc": "Хрупок, но одно заклинание меняет бой.",
        "spells": ["Магическая стрела", "Свет", "Сон"],
    },
    "cleric": {
        "name": "Клирик", "hit_die": 8,
        "start_items": ["Булава", "Щит", "Святой символ"],
        "desc": "Лечит раны и жжёт нежить верой.",
        "spells": ["Лечение ран", "Свет", "Защита от зла"],
    },
    "rogue": {
        "name": "Плут", "hit_die": 6,
        "start_items": ["Кинжал", "Отмычки", "Верёвка"],
        "desc": "Ловушки, тени, чужие карманы.",
    },
}

RACES = {
    "human":   {"name": "Человек", "mods": {}},
    "elf":     {"name": "Эльф", "mods": {"DEX": 1, "CON": -1}},
    "dwarf":   {"name": "Дварф", "mods": {"CON": 1, "CHA": -1}},
}


def mod(score: int) -> int:
    """Classic ability modifier."""
    return (score - 10) // 2


def new_character(name: str, race: str, cls: str) -> dict:
    if race not in RACES or cls not in CLASSES:
        raise ValueError("unknown race/class")
    stats = {s: roll_3d6() for s in STATS}
    for s, m in RACES[race]["mods"].items():
        stats[s] = max(3, min(18, stats[s] + m))
    c = CLASSES[cls]
    max_hp = c["hit_die"] + max(0, mod(stats["CON"]))
    return {
        "name": name[:24] or "Безымянный",
        "race": race,
        "class": cls,
        "level": 1,
        "xp": 0,
        "stats": stats,
        "hp": max_hp,
        "max_hp": max_hp,
        "gold": 30,
        "fate": 1,  # очко судьбы: один раз спасает от смерти за забег
        "inventory": list(c["start_items"]),
        "spells": list(c.get("spells", [])),
        "location": "Врата подземелья Кар-Морд",
        "depth": 1,
        "flags": {},
    }
