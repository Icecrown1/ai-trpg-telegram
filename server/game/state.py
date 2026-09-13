"""Apply the GM's state_delta to the character state.
The backend clamps everything — the model can propose, not dictate."""


def apply_delta(state: dict, delta: dict) -> dict:
    if not isinstance(delta, dict):
        return state

    if "hp" in delta:
        try:
            state["hp"] = max(0, min(state["max_hp"], state["hp"] + int(delta["hp"])))
        except (TypeError, ValueError):
            pass

    if "gold" in delta:
        try:
            state["gold"] = max(0, state["gold"] + int(delta["gold"]))
        except (TypeError, ValueError):
            pass

    if "xp" in delta:
        try:
            state["xp"] = max(0, state["xp"] + int(delta["xp"]))
        except (TypeError, ValueError):
            pass
        # simple level curve: 100 * current level
        while state["xp"] >= state["level"] * 100:
            state["xp"] -= state["level"] * 100
            state["level"] += 1
            state["max_hp"] += 4
            state["hp"] = state["max_hp"]  # level-up heals — a small mercy
            state["stat_points"] = int(state.get("stat_points", 0)) + 1
            if state["level"] % 2 == 0:
                state["talent_points"] = int(state.get("talent_points", 0)) + 1

    for item in delta.get("inventory_add", []) or []:
        if isinstance(item, str) and len(state["inventory"]) < 16:
            state["inventory"].append(item[:40])

    for item in delta.get("inventory_remove", []) or []:
        if item in state["inventory"]:
            state["inventory"].remove(item)

    if isinstance(delta.get("location"), str):
        state["location"] = delta["location"][:80]

    if "depth" in delta:
        try:
            state["depth"] = max(1, int(delta["depth"]))
        except (TypeError, ValueError):
            pass

    # ресурсы: resources_add / resources_remove = {"wood": 2}; рюкзак ограничен вместимостью
    from .resources import RESOURCES, backpack_load
    bp = state.setdefault("backpack", {"capacity": 8, "res": {}})
    if isinstance(delta.get("resources_add"), dict):
        for rid, cnt in delta["resources_add"].items():
            if rid not in RESOURCES:
                continue
            try:
                cnt = max(0, int(cnt))
            except (TypeError, ValueError):
                continue
            free = bp["capacity"] - backpack_load(bp["res"])
            take = min(cnt, max(0, free))
            if take:
                bp["res"][rid] = bp["res"].get(rid, 0) + take
    if isinstance(delta.get("resources_remove"), dict):
        for rid, cnt in delta["resources_remove"].items():
            if rid in bp["res"]:
                try:
                    bp["res"][rid] = max(0, bp["res"][rid] - max(0, int(cnt)))
                except (TypeError, ValueError):
                    continue
                if bp["res"][rid] == 0:
                    del bp["res"][rid]

    # износ снаряжения: equipment_damage: "armor" | "weapon"
    slot = delta.get("equipment_damage")
    if slot in ("armor", "weapon"):
        eq = state.setdefault("equipment", {})
        item = eq.get(slot)
        if item:
            item["dur"] = int(item.get("dur", 1)) - 1
            if item["dur"] <= 0:
                eq[slot] = None  # сломано безвозвратно

    # партия соратников: урон/лечение по имени, гибель или уход — party_remove
    party = state.setdefault("party", [])
    if isinstance(delta.get("party_hp"), dict):
        for name, dhp in delta["party_hp"].items():
            for m in party:
                if m.get("name") == name:
                    try:
                        m["hp"] = max(0, min(int(m.get("max_hp", 8)), int(m.get("hp", 0)) + int(dhp)))
                    except (TypeError, ValueError):
                        pass
    if isinstance(delta.get("party_remove"), list):
        gone = {str(x) for x in delta["party_remove"]}
        state["party"] = [m for m in party if m.get("name") not in gone]
    state["party"] = [m for m in state.get("party", []) if int(m.get("hp", 0)) > 0]

    if isinstance(delta.get("scene"), dict):
        sc = delta["scene"]
        clean = {}
        if isinstance(sc.get("place"), str):
            clean["place"] = sc["place"][:80]
        for key in ("exits", "objects", "beings"):
            if isinstance(sc.get(key), list):
                clean[key] = [str(x)[:60] for x in sc[key][:8] if isinstance(x, (str, int))]
        if clean:
            state["scene"] = {**state.get("scene", {}), **clean}

    if isinstance(delta.get("flags"), dict):
        state.setdefault("flags", {})
        for k, v in list(delta["flags"].items())[:10]:
            state["flags"][str(k)[:40]] = v if isinstance(v, (bool, int, str)) else str(v)
        # keep flags bounded
        if len(state["flags"]) > 30:
            for k in list(state["flags"].keys())[:-30]:
                del state["flags"][k]

    return state
