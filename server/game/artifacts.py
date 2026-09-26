"""Артефакты сокровищниц («золотые комнаты»). Меняют стиль игры, а не цифру.

Хранятся в инвентаре искателя по ТОЧНОМУ имени: переживают экстракцию, гибнут с искателем.
enforced: что сервер гарантирует сам; остальное обыгрывает мастер по правилу rule.
"""

ARTIFACTS = {
    "goblin_bone": {
        "name": "Кость Первого Гоблина",
        "desc": "Гоблины и звери считают тебя своим, пока ты не ударишь первым.",
        "rule": "гоблины и звери не нападают первыми и готовы говорить/торговать; как только носитель "
                "атакует гоблина или зверя, чары рвутся до конца забега (flags: {\"goblin_bone_broken\": true})",
    },
    "drowned_compass": {
        "name": "Компас утопленника",
        "desc": "Стрелка всегда смотрит на ближайший выход. Бегство из боя удаётся всегда — но что-то роняешь.",
        "rule": "всегда называй направление к ближайшему споту эвакуации; бегство из боя удаётся без броска, "
                "но носитель теряет 1 случайный ресурс из рюкзака (resources_remove)",
    },
    "eternal_candle": {
        "name": "Огарок неугасимой свечи",
        "desc": "Свет без рук, который не гаснет. Ловушки заметны заранее, СЛ заметить их ниже на 3.",
        "rule": "темнота носителю не мешает; каждую ловушку телеграфируй явно, проверки заметить/обезвредить "
                "ловушку — с modifier +3",
    },
    "greedy_purse": {
        "name": "Жадный кошель",
        "desc": "Всё найденное золото удваивается. Но кошель занимает место: рюкзак меньше на 2.",
        "rule": "золото в state_delta указывай обычное — сервер удвоит сам; рюкзак уже урезан сервером",
        "enforced": True,
    },
    "stone_heart": {
        "name": "Каменное сердце",
        "desc": "+5 к максимуму здоровья. Любое лечение действует вполовину.",
        "rule": "лечение указывай обычное — сервер сам урежет вдвое; обыгрывай тяжёлый медленный пульс",
        "enforced": True,
    },
    "seal_glove": {
        "name": "Перчатка сорванных печатей",
        "desc": "Двери, руны и сундуки поддаются легче: СЛ ниже на 3, повторная попытка без штрафа.",
        "rule": "проверки открытия дверей, рун, замков и сундуков — с modifier +3; повторная попытка "
                "идёт по той же СЛ, без +3",
    },
    "dead_mask": {
        "name": "Маска мертвеца",
        "desc": "Нежить не трогает тебя, пока ты её не тронешь. Живые шарахаются.",
        "rule": "нежить игнорирует носителя, пока он не атакует её; запугивание живых — modifier +3, "
                "убеждение живых — modifier -3",
    },
    "echo_shell": {
        "name": "Эхо-раковина",
        "desc": "Раз за забег сама перебрасывает твой первый проваленный бросок. Считается второй.",
        "rule": "сервер перебрасывает сам; если бросок помечен echo_reroll — опиши, как раковина отзывается "
                "эхом и мир на миг повторяется",
        "enforced": True,
    },
    "depth_fang": {
        "name": "Клык из глубин",
        "desc": "Оружие жжёт огнём: +1d4 урона при каждом попадании, сквозь завесы и нимбы. Но зверя в тебе слышно.",
        "rule": "сервер при попадании бросает огненный 1d4 (поле fire_bonus) — ПРИБАВЬ его к урону; огонь "
                "игнорирует завесы и нимбы боссов; случайные встречи с тварями чаще обычного",
        "enforced": True,
    },
    "gravedigger_clock": {
        "name": "Часы могильщика",
        "desc": "В каждом бою твой первый удар — как из засады.",
        "rule": "первая атака носителя в каждом новом бою всегда идёт с advantage_die: 6, и враг не отвечает "
                "на неё в этот ход",
    },
}

BY_NAME = {a["name"]: aid for aid, a in ARTIFACTS.items()}

GREEDY_CAPACITY_PENALTY = 2
MAX_PER_RUN = 3
STONE_HEART_HP = 5


def owned(state: dict) -> set:
    """id артефактов, которые сейчас в инвентаре."""
    return {BY_NAME[i] for i in (state.get("inventory") or []) if i in BY_NAME}


def capacity_penalty(inventory: list) -> int:
    return GREEDY_CAPACITY_PENALTY if ARTIFACTS["greedy_purse"]["name"] in (inventory or []) else 0


def adjust_delta(state: dict, delta: dict) -> dict:
    """Серверные эффекты ДО применения дельты: кошель удваивает золото, сердце режет лечение."""
    have = owned(state)
    d = dict(delta or {})
    if "greedy_purse" in have:
        try:
            g = int(d.get("gold", 0) or 0)
            if g > 0:
                d["gold"] = g * 2
        except (TypeError, ValueError):
            pass
    if "stone_heart" in have:
        try:
            h = int(d.get("hp", 0) or 0)
            if h > 0:
                d["hp"] = max(1, h // 2)
        except (TypeError, ValueError):
            pass
    return d


def apply_transitions(old: dict, new: dict) -> dict:
    """Артефакт появился или пропал за ход — сразу меняем максимум HP и рюкзак."""
    before, after = owned(old), owned(new)
    gained, lost = after - before, before - after
    # лимит артефактов на забег: лишние из дельты мастера не оседают
    flags = new.setdefault("flags", {})
    found = int(flags.get("artifacts_found", 0) or 0)
    allowed = sorted(gained)[:max(0, MAX_PER_RUN - found)]
    for aid in gained - set(allowed):
        name = ARTIFACTS[aid]["name"]
        new["inventory"] = [i for i in new.get("inventory") or [] if i != name]
    gained = set(allowed)
    if gained:
        flags["artifacts_found"] = found + len(gained)
    if "stone_heart" in gained:
        new["max_hp"] = int(new["max_hp"]) + STONE_HEART_HP
        new["hp"] = int(new["hp"]) + STONE_HEART_HP
    if "stone_heart" in lost:
        new["max_hp"] = max(1, int(new["max_hp"]) - STONE_HEART_HP)
        new["hp"] = min(int(new["hp"]), new["max_hp"])
    bp = new.get("backpack")
    if bp is not None:
        if "greedy_purse" in gained:
            bp["capacity"] = max(2, int(bp["capacity"]) - GREEDY_CAPACITY_PENALTY)
        if "greedy_purse" in lost:
            bp["capacity"] = int(bp["capacity"]) + GREEDY_CAPACITY_PENALTY
    # артефакты уникальны: дубль из дельты мастера не оседает в инвентаре
    seen, inv = set(), []
    for item in new.get("inventory") or []:
        if item in BY_NAME:
            if item in seen:
                continue
            seen.add(item)
        inv.append(item)
    new["inventory"] = inv
    return new
