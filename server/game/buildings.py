"""Здания города: стоимости уровней и что они дают."""

BUILDING_DEFS = {
    # Ур.1 — из простого сырья (несколько походов на первые ярусы), выше — редкое сырьё глубин
    # и крафтовые материалы других зданий (брус таверны, слитки и тёсаный камень кузницы, руны башни).
    "tavern": {
        "name": "Таверна",
        "levels": {
            1: {"cost": {"wood": 3, "stone": 3}, "gold": 0,
                "desc": "Крыша, свет в окнах, эль: путники потянутся. Пип пилит брус"},
            2: {"cost": {"beam": 4, "stone": 6, "leather": 3}, "gold": 60,
                "requires_flag": "barman_dead",
                "desc": "+1 стол соратников, новые лица"},
        },
    },
    "throne": {
        "name": "Тронный зал",
        "levels": {
            1: {"cost": {"stone": 10, "wood": 8, "leather": 2}, "gold": 40,
                "desc": "+1 слот искателя, +1 слот соратника, поручения трона"},
            2: {"cost": {"cut_stone": 6, "beam": 6, "iron_ingot": 3}, "gold": 150,
                "desc": "+1 слот искателя, +2 слота соратников"},
            3: {"cost": {"cut_stone": 10, "rune_stone": 2, "iron_ingot": 6, "mithril": 2}, "gold": 500,
                "desc": "+1 слот искателя, +2 слота соратников"},
        },
    },
    "forge": {"name": "Кузница", "locked_by": "dwarf_saved",
              "locked_text": "Нужно спасти дварфа-кузнеца в глубинах Кар-Морда",
              "levels": {
                  1: {"cost": {"stone": 8, "wood": 6, "iron": 2}, "gold": 50,
                      "desc": "Торин у горна: простой крафт и слитки железа"},
                  2: {"cost": {"beam": 4, "iron_ingot": 4, "wood_hard": 3}, "gold": 150,
                      "desc": "Калёная сталь, кольчуги и тёсаный камень для ратуши"},
                  3: {"cost": {"cut_stone": 6, "iron_ingot": 8, "mithril": 4}, "gold": 500,
                      "desc": "Мифрил поёт под молотом"},
              }},
    "mage_tower": {"name": "Башня мага", "locked_by": "mage_saved",
                   "locked_text": "Нужно найти и спасти мага в подземельях",
                   "levels": {
                       1: {"cost": {"cloth": 4, "wood": 6, "stone": 4}, "gold": 60,
                           "desc": "Финеус въезжает: свитки исцеления, свет, заговорённая ткань"},
                       2: {"cost": {"cut_stone": 4, "enchanted_cloth": 3, "ash_essence": 2}, "gold": 180,
                           "desc": "Каменная кожа, призрачные клинки, рунный камень"},
                       3: {"cost": {"rune_stone": 3, "soul_shard": 2, "enchanted_cloth": 4}, "gold": 500,
                           "desc": "«Наконец-то настоящая наука!» — последний вздох и огненная плеть"},
                   }},
}


def seeker_slots(buildings: dict) -> int:
    return 1 + int((buildings or {}).get("throne", 0))


def companion_slots(buildings: dict) -> int:
    throne = int((buildings or {}).get("throne", 0))
    return {0: 1, 1: 2, 2: 4}.get(throne, 6)
