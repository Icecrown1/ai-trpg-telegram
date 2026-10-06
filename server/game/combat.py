"""Бой: инициатива и очередь ходов. Кубики инициативы бросает сервер, мастер ведёт раунд по очереди.

state["combat"] = {"round": n, "order": [{name, side: ally|enemy, init, hp, max_hp, id?, you?}]}
Мастер управляет боем через state_delta.combat:
  {"start": [{"name": "Гоблин 1", "id": "goblin", "hp": 7}], "enemy_hp": {"Гоблин 1": -4}, "end": true}
"""
import secrets

from . import bestiary as _bestiary

_QUICK = {"rogue", "archer", "druid"}  # соратники-ловкачи: +2 к инициативе


def _d20() -> int:
    return secrets.randbelow(20) + 1


def _mod(score) -> int:
    return (int(score or 10) - 10) // 2


def _enemy_entry(raw: dict, depth: int):
    if not isinstance(raw, dict) or not str(raw.get("name") or "").strip():
        return None
    foe = _bestiary.get(raw.get("id")) if raw.get("id") else None
    try:
        hp = int(raw.get("hp") or (foe or {}).get("hp") or 6)
    except (TypeError, ValueError):
        hp = 6
    hp = max(1, min(80, hp))
    bonus = int((foe or {}).get("atk", 2)) // 2
    roll = _d20()
    return {"name": str(raw["name"]).strip()[:32], "side": "enemy", "id": raw.get("id"),
            "init": roll + bonus, "roll": roll, "hp": hp, "max_hp": hp}


def _allies(state: dict) -> list:
    you = {"name": "Ты", "side": "ally", "you": True, "hp": state.get("hp"), "max_hp": state.get("max_hp")}
    out = [you]
    for m in state.get("party") or []:
        out.append({"name": m.get("name"), "side": "ally", "hp": m.get("hp"), "max_hp": m.get("max_hp"),
                    "cls": m.get("cls")})
    return out


def _sort(order: list) -> list:
    # ничья по инициативе — выше тот, у кого выше чистый бросок, дальше союзник
    return sorted(order, key=lambda e: (-int(e.get("init", 0)), -int(e.get("roll", 0)),
                                        0 if e.get("side") == "ally" else 1))


def _sync_allies(state: dict, order: list) -> list:
    """HP союзников в очереди всегда как в листе персонажа; павшие выбывают."""
    party = {m.get("name"): m for m in state.get("party") or []}
    out = []
    for e in order:
        if e.get("side") == "ally":
            if e.get("you"):
                e["hp"], e["max_hp"] = state.get("hp"), state.get("max_hp")
            elif e.get("name") in party:
                e["hp"], e["max_hp"] = party[e["name"]].get("hp"), party[e["name"]].get("max_hp")
            else:
                continue
        out.append(e)
    return out


def apply(state: dict, cdelta, depth: int = 1) -> str:
    """Применить state_delta.combat. Возвращает строку для повествования (или '')."""
    notes = []
    combat = state.get("combat")
    if isinstance(cdelta, dict) and isinstance(cdelta.get("start"), list) and cdelta["start"]:
        foes = [e for e in (_enemy_entry(r, depth) for r in cdelta["start"][:8]) if e]
        if foes:
            if not combat:
                allies = []
                for a in _allies(state):
                    roll = _d20()
                    bonus = _mod((state.get("stats") or {}).get("DEX")) if a.get("you") \
                        else (2 if a.get("cls") in _QUICK else 0)
                    allies.append({**a, "init": roll + bonus, "roll": roll})
                combat = {"round": 1, "order": _sort(allies + foes)}
                notes.append("⚔ БОЙ. Инициатива: " + " · ".join(
                    f'{e["name"]} {e["init"]}' for e in combat["order"]))
            else:  # подкрепление встаёт в очередь со своей инициативой
                known = {e["name"] for e in combat["order"]}
                fresh = [f for f in foes if f["name"] not in known]
                combat["order"] = _sort(combat["order"] + fresh)
                if fresh:
                    notes.append("⚔ В бой вступают: " + ", ".join(f'{f["name"]} (иниц. {f["init"]})' for f in fresh))
    elif combat:
        combat["round"] = int(combat.get("round", 1)) + 1

    if combat and isinstance(cdelta, dict) and isinstance(cdelta.get("enemy_hp"), dict):
        for name, dhp in cdelta["enemy_hp"].items():
            for e in combat["order"]:
                if e.get("side") == "enemy" and e.get("name") == name:
                    try:
                        e["hp"] = max(0, min(int(e["max_hp"]), int(e["hp"]) + int(dhp)))
                    except (TypeError, ValueError):
                        pass
    if combat:
        combat["order"] = [e for e in _sync_allies(state, combat["order"])
                           if not (e.get("side") == "enemy" and int(e.get("hp", 0)) <= 0)]
        enemies_left = any(e.get("side") == "enemy" for e in combat["order"])
        if (isinstance(cdelta, dict) and cdelta.get("end")) or not enemies_left:
            combat = None
            notes.append("Бой окончен.")
    state["combat"] = combat
    return "\n".join(notes)


def brief(state: dict):
    """Очередь боя для мастера: кто за кем ходит в этом раунде."""
    c = state.get("combat")
    if not c:
        return None
    line = []
    for e in c.get("order", []):
        who = "ты" if e.get("you") else ("союзник" if e.get("side") == "ally" else "враг")
        line.append(f'{e["name"]} ({who}, иниц. {e.get("init")}, HP {e.get("hp")}/{e.get("max_hp")})')
    return {"раунд": c.get("round", 1), "очередь": line,
            "как вести": "раунд целиком по очереди сверху вниз: враги действуют в своих местах очереди, "
                         "союзники — по приказам игрока (он командует всеми своими); урон врагам — combat.enemy_hp"}


def hits_on_player(rolls: list) -> list:
    """Удары, пришедшиеся по игроку: бросок урона сразу после попавшей вражеской атаки."""
    hits, armed = [], False
    for r in rolls or []:
        kind = r.get("kind")
        if kind == "enemy_attack":
            armed = bool(r.get("success"))
            continue
        if kind == "damage" and armed:
            hits.append(int(r.get("total", 0) or 0))
            armed = False
            continue
        armed = False
    return hits


def absorb_with_ward(state: dict, delta: dict, rolls: list):
    """Синие сердца: каждое целиком гасит один пропущенный удар. Возвращает (delta, заметка)."""
    ward = int(state.get("ward", 0) or 0)
    try:
        dmg = -int((delta or {}).get("hp", 0) or 0)
    except (TypeError, ValueError):
        dmg = 0
    if ward <= 0 or dmg <= 0:
        return delta, ""
    hits = sorted(hits_on_player(rolls), reverse=True) or [dmg]
    blocked, used = 0, 0
    for h in hits:
        if used >= ward or blocked >= dmg:
            break
        blocked += min(h, dmg - blocked)
        used += 1
    if not used:
        return delta, ""
    d = dict(delta)
    d["hp"] = -(dmg - blocked)
    state["ward"] = ward - used
    return d, f"💙 Синее сердце принимает удар: −{blocked} HP не прошло (осталось сердец: {ward - used})."
