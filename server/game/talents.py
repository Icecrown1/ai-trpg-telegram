"""Каталог талантов. mech: серверное принуждение; narrative: обыгрывает мастер."""

TALENTS = {
    "beast_speech": {"name": "Разговор с животными", "kind": "narrative",
                     "desc": "Звери и твари со звериным умом понимают тебя и могут ответить."},
    "darkvision":   {"name": "Тёмное зрение", "kind": "narrative",
                     "desc": "Темнота не даёт штрафов твоим проверкам."},
    "scavenger":    {"name": "Мародёр", "kind": "narrative",
                     "desc": "Находишь ценное там, где другие видят мусор: больше находок и ресурсов."},
    "silver_tongue": {"name": "Златоуст", "kind": "stat_bonus", "stat": "CHA", "bonus": 1,
                      "desc": "+1 ко всем проверкам Харизмы."},
    "keen_senses":  {"name": "Чуткие чувства", "kind": "stat_bonus", "stat": "WIS", "bonus": 1,
                     "desc": "+1 ко всем проверкам Мудрости."},
    "blade_dancer": {"name": "Танец клинка", "kind": "attack_bonus", "bonus": 1,
                     "desc": "+1 ко всем атакам."},
    "stone_hide":   {"name": "Дублёная шкура", "kind": "defense_bonus", "bonus": 1,
                     "desc": "+1 к защите: по тебе труднее попасть."},
    "strong_back":  {"name": "Крепкая спина", "kind": "capacity_bonus", "bonus": 2,
                     "desc": "+2 слота рюкзака."},
}


def stat_check_bonus(talents: list, stat: str) -> int:
    b = 0
    for t in talents or []:
        td = TALENTS.get(t)
        if td and td["kind"] == "stat_bonus" and td["stat"] == stat:
            b += td["bonus"]
    return b


def attack_bonus(talents: list) -> int:
    return sum(TALENTS[t]["bonus"] for t in talents or []
               if t in TALENTS and TALENTS[t]["kind"] == "attack_bonus")


def defense_bonus(talents: list) -> int:
    return sum(TALENTS[t]["bonus"] for t in talents or []
               if t in TALENTS and TALENTS[t]["kind"] == "defense_bonus")


def capacity_bonus(talents: list) -> int:
    return sum(TALENTS[t]["bonus"] for t in talents or []
               if t in TALENTS and TALENTS[t]["kind"] == "capacity_bonus")
