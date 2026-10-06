"""Apply the GM's state_delta to the character state.
The backend clamps everything — the model can propose, not dictate."""


def _norm(name: str) -> str:
    return " ".join(str(name).lower().replace("ё", "е").split())


def dedupe_items(items: list) -> list:
    """Убирает повторы предметов (без учёта регистра и лишних пробелов), порядок сохраняется."""
    seen, out = set(), []
    for i in items or []:
        k = _norm(i)
        if k and k not in seen:
            seen.add(k)
            out.append(i)
    return out


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

    # инвентарь без дублей: одна вещь — одна строка (мастер любит «находить» уже имеющееся)
    state["inventory"] = dedupe_items(state.get("inventory") or [])
    have = {_norm(i) for i in state["inventory"]}
    for item in delta.get("inventory_add", []) or []:
        if isinstance(item, str) and item.strip() and len(state["inventory"]) < 16:
            name = item.strip()[:40]
            if _norm(name) in have:
                continue
            state["inventory"].append(name)
            have.add(_norm(name))

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
    from .resources import RESOURCES, room_for, BACKPACK_CAPACITY_DEFAULT
    bp = state.setdefault("backpack", {"capacity": BACKPACK_CAPACITY_DEFAULT, "res": {}})
    if isinstance(delta.get("resources_add"), dict):
        for rid, cnt in delta["resources_add"].items():
            if rid not in RESOURCES or RESOURCES[rid].get("crafted"):
                continue  # крафтовое из подземелья не выносят — его делают в городе
            try:
                cnt = max(0, int(cnt))
            except (TypeError, ValueError):
                continue
            take = min(cnt, room_for(bp, rid))
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

    # находки-снаряжение: в сумку (лимит), лишнее остаётся лежать на полу этого места
    from .gear import sanitize_gear, BAG_LIMIT
    if isinstance(delta.get("gear_add"), list):
        bag = state.setdefault("bag", [])
        have = {_norm(b.get("name")) for b in bag} | {
            _norm((v or {}).get("name")) for v in (state.get("equipment") or {}).values() if isinstance(v, dict)}
        for raw in delta["gear_add"][:4]:
            it = sanitize_gear(raw, state.get("depth", 1))
            if not it or _norm(it["name"]) in have:
                continue
            have.add(_norm(it["name"]))
            if len(bag) < BAG_LIMIT:
                bag.append(it)
            else:
                place = (state.get("scene") or {}).get("place") or state.get("location")
                fl = state.get("floor") or {}
                if fl.get("place") != place:
                    fl = {"place": place, "res": {}, "items": [], "gear": []}
                fl.setdefault("gear", []).append(it)
                state["floor"] = fl

    # синие сердца: редкое благословение мастера (не больше одного за ход)
    if delta.get("ward_add"):
        try:
            state["ward"] = min(6, int(state.get("ward", 0) or 0) + max(0, min(1, int(delta["ward_add"]))))
        except (TypeError, ValueError):
            pass

    # износ снаряжения: equipment_damage: "armor" | "weapon" | "head" | "offhand"
    slot = delta.get("equipment_damage")
    if slot in ("armor", "weapon", "head", "offhand"):
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
    # завербованный враг или спасённый пленник встаёт в строй
    if isinstance(delta.get("party_add"), list):
        names = {m.get("name") for m in party}
        for m in delta["party_add"][:2]:
            if not isinstance(m, dict) or not str(m.get("name") or "").strip():
                continue
            name = str(m["name"]).strip()[:32]
            if name in names or len(party) >= 4:
                continue
            try:
                mhp = max(1, min(20, int(m.get("max_hp") or m.get("hp") or 8)))
            except (TypeError, ValueError):
                mhp = 8
            party.append({"name": name, "cls": str(m.get("cls") or "")[:16],
                          "cls_name": str(m.get("cls_name") or m.get("cls") or "союзник")[:24],
                          "hp": mhp, "max_hp": mhp, "loyalty": 0, "recruited": True})
            names.add(name)

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
