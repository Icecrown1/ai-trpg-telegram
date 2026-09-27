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


# --- Страховка: сырьё, которое мастер по ошибке положил в снаряжение, уезжает в рюкзак ---
import re as _re

# корень слова -> ресурс (порядок важен: сначала более редкие)
_MATERIAL_ROOTS = [
    (r"живо\w* золот", "living_gold"),
    (r"осколо?к\w* душ", "soul_shard"),
    (r"пепельн\w* эссенц", "ash_essence"),
    (r"мифрил", "mithril"),
    (r"зачарованн\w* дерев|зачарованн\w* древесин", "wood_enchanted"),
    (r"прочн\w* дерев|морён\w* дуб|желез\w* дерев", "wood_hard"),
    (r"\bруд[аыу]\b|рудн|слит\w* желез|железн\w* руд|крица", "iron"),
    (r"\bкамн|\bкамень|булыжн|гранит|кладк|щебен|щебён", "stone"),
    (r"\bдерев|древесин|\bдоск|бревн|полен|брус\b|щеп", "wood"),
    (r"\bшкур|\bкож[аиуе]\b|сыромят", "leather"),
    (r"\bткан|тряп|лоскут|полотн|холст|сукн|мешковин|обрывк\w* ряс", "cloth"),
    (r"\bкост[иьея]|\bкость\b|позвон|\bчереп|\bрог[аи]?\b|\bклык", "bone"),
]
# слова, делающие вещь ИЗДЕЛИЕМ, а не сырьём
_CRAFTED = _re.compile(
    r"меч|нож|кинжал|топор|кирк|молот|лук\b|стрел|щит|шлем|доспех|нагрудник|латы|сапог|ботин|перчат|ремень|"
    r"пояс|сумк|мешоч|кошел|фляг|бутыл|книг|свит|карт|ключ|амулет|кольц|посох|жезл|факел|верёвк|веревк|"
    r"цеп|крюк|кошк|лом\b|отмычк|статуэт|идол|кубок|чаш|маск|плащ|куртк|капюшон|рукоят|ножн|труб|свисток|"
    r"первого гоблина|из глубин|сердце", _re.I)


def material_of(item: str):
    """Если предмет по названию — сырьё, вернуть id ресурса, иначе None."""
    name = str(item).lower().replace("ё", "е")
    if _CRAFTED.search(name):
        return None
    for pattern, rid in _MATERIAL_ROOTS:
        if _re.search(pattern.replace("ё", "е"), name):
            return rid
    return None


def reroute_materials(delta: dict) -> dict:
    """Переносит сырьё из inventory_add в resources_add. Возвращает новую дельту."""
    d = dict(delta or {})
    adds = list(d.get("inventory_add") or [])
    if not adds:
        return d
    keep, res = [], dict(d.get("resources_add") or {})
    for item in adds:
        rid = material_of(item) if isinstance(item, str) else None
        if rid:
            res[rid] = int(res.get(rid, 0)) + 1
        else:
            keep.append(item)
    d["inventory_add"] = keep
    if res:
        d["resources_add"] = res
    return d
