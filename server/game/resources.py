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
    # --- крафтовое: в подземелье не встречается, его делают здания города ---
    "beam":            {"name": "Брус", "tier": 2, "crafted": True},
    "iron_ingot":      {"name": "Слиток железа", "tier": 2, "crafted": True},
    "cut_stone":       {"name": "Тёсаный камень", "tier": 3, "crafted": True},
    "enchanted_cloth": {"name": "Заговорённая ткань", "tier": 3, "crafted": True},
    "rune_stone":      {"name": "Рунный камень", "tier": 4, "crafted": True},
}

# Переработка в городе: здание нужного уровня превращает сырьё в крафтовые материалы.
# Высокие уровни зданий строятся из них — одним походом на первый ярус город не поднять.
RECIPES = {
    "beam":            {"out": "beam", "building": "tavern", "level": 1, "in": {"wood": 3}, "gold": 0,
                        "who": "Пип пилит брёвна во дворе таверны"},
    "iron_ingot":      {"out": "iron_ingot", "building": "forge", "level": 1, "in": {"iron": 2}, "gold": 5,
                        "who": "Торин плавит руду в слитки"},
    "cut_stone":       {"out": "cut_stone", "building": "forge", "level": 2, "in": {"stone": 3, "iron_ingot": 1},
                        "gold": 10, "who": "калёным зубилом Торин тешет камень под кладку"},
    "enchanted_cloth": {"out": "enchanted_cloth", "building": "mage_tower", "level": 1,
                        "in": {"cloth": 2, "ash_essence": 1}, "gold": 15, "who": "Финеус вплетает пепел в нить"},
    "rune_stone":      {"out": "rune_stone", "building": "mage_tower", "level": 2,
                        "in": {"cut_stone": 1, "soul_shard": 1}, "gold": 40, "who": "Финеус режет руны по тёсаному камню"},
}


def cost_list(cost: dict, have: dict, gold: int = 0, have_gold: int = 0) -> list:
    """Для UI «есть / нужно»: каждая позиция цены с запасом склада."""
    out = [{"id": rid, "name": RESOURCES.get(rid, {}).get("name", rid), "need": int(n),
            "have": int((have or {}).get(rid, 0)), "ok": int((have or {}).get(rid, 0)) >= int(n)}
           for rid, n in (cost or {}).items()]
    if gold:
        out.append({"id": "gold", "name": "Золото", "need": int(gold), "have": int(have_gold or 0),
                    "ok": int(have_gold or 0) >= int(gold)})
    return out

BACKPACK_CAPACITY_DEFAULT = 12  # слотов; рюкзаки кузницы поднимают до 16 / 20 / 24
STACK_SIZE = 3                  # одинаковых ресурсов в слоте; подписки поднимут до 6 / 9
STACK_BY_TIER = {"free": 3, "sub": 6, "premium": 9}


def stack_of(bp: dict) -> int:
    return max(1, int((bp or {}).get("stack") or STACK_SIZE))


def slots_for(cnt: int, stack: int = STACK_SIZE) -> int:
    cnt = max(0, int(cnt))
    return (cnt + stack - 1) // stack


def backpack_load(res: dict, stack: int = STACK_SIZE) -> int:
    """Занятые СЛОТЫ: каждый ресурс — стопками по stack штук."""
    return sum(slots_for(v, stack) for v in (res or {}).values())


def room_for(bp: dict, rid: str) -> int:
    """Сколько ещё единиц ресурса rid влезет в рюкзак с учётом стопок."""
    stack = stack_of(bp)
    res = (bp or {}).get("res") or {}
    others = backpack_load({k: v for k, v in res.items() if k != rid}, stack)
    allowed = max(0, int((bp or {}).get("capacity", BACKPACK_CAPACITY_DEFAULT)) - others) * stack
    return max(0, allowed - int(res.get(rid, 0)))


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
    """Переносит сырьё из inventory_add в resources_add, а оружие и доспехи — в gear_add.
    Возвращает новую дельту."""
    from .gear import gear_from_name
    d = dict(delta or {})
    adds = list(d.get("inventory_add") or [])
    if not adds:
        return d
    keep, res = [], dict(d.get("resources_add") or {})
    gear = list(d.get("gear_add") or [])
    for item in adds:
        rid = material_of(item) if isinstance(item, str) else None
        if rid:
            res[rid] = int(res.get(rid, 0)) + 1
        elif isinstance(item, str) and gear_from_name(item):
            gear.append(item)
        else:
            keep.append(item)
    d["inventory_add"] = keep
    if gear:
        d["gear_add"] = gear
    if res:
        d["resources_add"] = res
    return d


# С какой глубины встречается сырьё: редкое не выпадает на мелководье (экономика города)
MIN_DEPTH = {"iron": 2, "wood_hard": 2, "ash_essence": 2, "mithril": 3, "wood_enchanted": 3,
             "soul_shard": 3, "living_gold": 5}
_DOWNGRADE = {"iron": "stone", "wood_hard": "wood", "mithril": "iron", "wood_enchanted": "wood_hard"}
TURN_CAP = {1: 2, 2: 3}  # максимум единиц сырья за один ход на мелких глубинах


def clamp_by_depth(delta: dict, depth: int) -> dict:
    """Сырьё не по глубине — понижается до простого или отбрасывается; за ход — не больше лимита."""
    d = dict(delta or {})
    add = d.get("resources_add")
    if not isinstance(add, dict) or not add:
        return d
    depth = max(1, int(depth or 1))
    out = {}
    for rid, cnt in add.items():
        try:
            cnt = max(0, int(cnt))
        except (TypeError, ValueError):
            continue
        while rid and MIN_DEPTH.get(rid, 1) > depth:
            rid = _DOWNGRADE.get(rid)
        if rid:
            out[rid] = out.get(rid, 0) + cnt
    cap = TURN_CAP.get(depth)
    if cap:
        total, capped = 0, {}
        for rid, cnt in out.items():
            take = min(cnt, cap - total)
            if take > 0:
                capped[rid] = take
                total += take
        out = capped
    d["resources_add"] = out
    return d
