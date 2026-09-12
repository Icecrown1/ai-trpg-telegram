"""Каталог ресурсов экстракшн-слоя. Вес каждого = 1 слот рюкзака."""

RESOURCES = {
    "wood":            {"name": "Дерево", "tier": 1},
    "wood_hard":       {"name": "Прочное дерево", "tier": 2},
    "wood_enchanted":  {"name": "Зачарованное дерево", "tier": 3},
    "stone":           {"name": "Камень", "tier": 1},
    "iron":            {"name": "Железная руда", "tier": 2},
    "mithril":         {"name": "Мифриловая руда", "tier": 3},
    "leather":         {"name": "Кожа", "tier": 1},
    "cloth":           {"name": "Ткань", "tier": 1},
    "bone":            {"name": "Кость чудовища", "tier": 2},
    "ash_essence":     {"name": "Пепельная эссенция", "tier": 3},
    "soul_shard":      {"name": "Осколок души", "tier": 3},
    "living_gold":     {"name": "Живое золото", "tier": 4},
}

BACKPACK_CAPACITY_DEFAULT = 8


def backpack_load(res: dict) -> int:
    return sum(int(v) for v in (res or {}).values())


def res_brief(res: dict) -> dict:
    """Человекочитаемый вид для брифа мастеру и UI."""
    return {RESOURCES[k]["name"]: v for k, v in (res or {}).items() if k in RESOURCES}
