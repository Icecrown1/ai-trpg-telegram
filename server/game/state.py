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
