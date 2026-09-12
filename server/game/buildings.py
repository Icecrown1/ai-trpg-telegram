"""Здания города: стоимости уровней и что они дают."""

BUILDING_DEFS = {
    "tavern": {
        "name": "Таверна",
        "levels": {
            2: {"cost": {"wood": 8, "stone": 4}, "gold": 40,
                "requires_flag": "barman_dead",
                "desc": "+1 стол соратников, новые лица"},
        },
    },
    "throne": {
        "name": "Тронный зал",
        "levels": {
            1: {"cost": {"stone": 6, "wood": 4}, "gold": 30, "desc": "+1 слот искателя, +1 слот соратника"},
            2: {"cost": {"stone": 12, "iron": 6}, "gold": 120, "desc": "+1 слот искателя, +2 слота соратников"},
            3: {"cost": {"iron": 10, "mithril": 3, "wood_enchanted": 2}, "gold": 400,
                "desc": "+1 слот искателя, +2 слота соратников"},
        },
    },
    "forge": {"name": "Кузница", "locked_by": "dwarf_saved",
              "locked_text": "Нужно спасти дварфа-кузнеца в глубинах Кар-Морда",
              "levels": {
                  1: {"cost": {"wood": 6, "stone": 6}, "gold": 50, "desc": "Торин у горна: простой крафт"},
                  2: {"cost": {"iron": 8, "wood_hard": 4}, "gold": 150, "desc": "Калёная сталь и кольчуги"},
                  3: {"cost": {"mithril": 4, "iron": 6}, "gold": 500, "desc": "Мифрил поёт под молотом"},
              }},
    "mage_tower": {"name": "Башня мага", "locked_by": "mage_saved",
                   "locked_text": "Нужно найти и спасти мага в подземельях",
                   "levels": {
                       1: {"cost": {"cloth": 4, "wood": 4}, "gold": 60,
                           "desc": "Финеус въезжает: свитки исцеления и свет"},
                       2: {"cost": {"ash_essence": 3, "stone": 6}, "gold": 180,
                           "desc": "Каменная кожа и призрачные клинки"},
                       3: {"cost": {"soul_shard": 2, "ash_essence": 3}, "gold": 500,
                           "desc": "«Наконец-то настоящая наука!» — последний вздох и огненная плеть"},
                   }},
}


def seeker_slots(buildings: dict) -> int:
    return 1 + int((buildings or {}).get("throne", 0))


def companion_slots(buildings: dict) -> int:
    throne = int((buildings or {}).get("throne", 0))
    return {0: 1, 1: 2, 2: 4}.get(throne, 6)
