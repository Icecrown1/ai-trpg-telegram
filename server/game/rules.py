"""Character rules in the spirit of PLATO dnd / AD&D. All numbers server-side."""
from ..dice import roll_3d6
from .resources import BACKPACK_CAPACITY_DEFAULT

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
    "archer": {
        "name": "Лучник", "hit_die": 8,
        "start_items": ["Короткий лук", "Колчан стрел", "Охотничий нож"],
        "desc": "Смерть с расстояния. Ловкость решает.",
    },
    "templar": {
        "name": "Храмовник", "hit_die": 10,
        "start_items": ["Двуручный меч", "Латный нагрудник", "Обет на пергаменте"],
        "desc": "Сталь и вера в одном ударе. Медлителен, но неумолим.",
        "spells": ["Кара света", "Стойкость"],
    },
    "druid": {
        "name": "Друид", "hit_die": 8,
        "start_items": ["Посох из живого дуба", "Мешочек трав", "Костяной амулет"],
        "desc": "Говорит с тем, что растёт и рычит.",
        "spells": ["Опутывание", "Лечение природой", "Звериный облик"],
        "talents": ["beast_speech"],
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


def seeker_to_state(seeker, dungeon: dict, name_override=None) -> dict:
    """Собрать боевое состояние из персистентного искателя."""
    c = CLASSES[seeker.cls]
    eq = dict(seeker.equipment or {})
    from .talents import capacity_bonus
    talents = list(seeker.talents or [])
    pack_bonus = int((eq.get("pack") or {}).get("capacity", 0)) + capacity_bonus(talents)
    return {
        "name": name_override or seeker.name,
        "race": seeker.race, "class": seeker.cls,
        "level": seeker.level, "xp": seeker.xp,
        "stats": dict(seeker.stats),
        "hp": seeker.max_hp, "max_hp": seeker.max_hp,
        "gold": 30,
        "inventory": list(seeker.inventory) if seeker.inventory else list(c["start_items"]),
        "spells": list(c.get("spells", [])),
        "location": dungeon["start_location"], "depth": 1, "flags": {},
        "fate": 1,
        "backpack": {"capacity": 8 + pack_bonus, "res": {}},
        "equipment": eq,
        "talents": talents,
        "stat_points": int(seeker.stat_points or 0),
        "talent_points": int(seeker.talent_points or 0),
        "scene": {"place": dungeon["start_location"],
                  "exits": list(dungeon["start_exits"]), "objects": [], "beings": []},
        "party": [],
    }


def new_character(name: str, race: str, cls: str, dungeon: dict = None) -> dict:
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
        "backpack": {"capacity": BACKPACK_CAPACITY_DEFAULT, "res": {}},
        "equipment": {},
        "talents": list(c.get("talents", [])),
        "stat_points": 0,
        "talent_points": 0,
        "inventory": list(c["start_items"]),
        "spells": list(c.get("spells", [])),
        "location": (dungeon or {}).get("start_location", "Врата подземелья Кар-Морд"),
        "scene": {"place": (dungeon or {}).get("start_location", "Врата подземелья Кар-Морд"),
                  "exits": list((dungeon or {}).get("start_exits", ["внутрь, за врата"])),
                  "objects": [], "beings": []},
        "depth": 1,
        "flags": {},
    }
