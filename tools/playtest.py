"""Бот-игрок: играет забеги с НАСТОЯЩИМ мастером и пишет протокол для разбора.

Запуск в Replit Shell (ключи берутся из Secrets):
    python tools/playtest.py                       # 1 забег в Кар-Морд, до 25 ходов
    python tools/playtest.py --dungeon all         # по забегу в каждый данж
    python tools/playtest.py --dungeon forest --turns 40 --class druid --race elf

Игра идёт в ОТДЕЛЬНОЙ базе playtest.db — прод-данные и лимиты игроков не трогаются.
Итог: файл playtest_<время>.md в корне проекта — его и присылай на разбор.
"""
import argparse
import os
import re
import random
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# отдельная песочница: не трогаем прод-базу и лимиты
DB_FILE = ROOT / "playtest.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["ALLOW_DEV_AUTH"] = "1"
os.environ["RUNS_PER_WINDOW"] = "999"
os.environ["FREE_TURNS_PER_DAY"] = "100000"

if DB_FILE.exists():
    DB_FILE.unlink()

from fastapi.testclient import TestClient  # noqa: E402
from server.main import app  # noqa: E402
from server.game.resources import material_of, RESOURCES  # noqa: E402

LOOT_WORDS = ("обыск", "осмотр", "взять", "подобр", "развед", "разделат", "сундук", "ящик", "тайник",
              "вскры", "собрат", "добы", "руб", "копат", "шкур", "исслед")
FIGHT_WORDS = ("атак", "удар", "бить", "руб", "стрел", "напас", "рубануть", "ударить")
EXIT_WORDS = ("выход", "выбрат", "подъём", "подъемник", "эвакуац", "врат", "уйти", "отступ", "тракт",
              "опушк", "жёлоб", "желоб", "окно")

CUSTOM = [
    "Обыскиваю всё вокруг и забираю полезное, особенно материалы для города",
    "Разделываю убитых тварей: снимаю шкуры, срезаю кости",
    "Ищу сокровищницу этой глубины — прислушиваюсь к сквозняку и ищу блеск",
    "Спускаюсь глубже",
    "Готовлю засаду в тени и бью первым, когда враг подойдёт",
    "Атакую размашистым ударом всех ближайших врагов разом",
    "Осторожно проверяю пол и стены на ловушки, прежде чем идти дальше",
    "Заговариваю с ближайшим существом и пытаюсь выторговать сведения",
]
LATIN = re.compile(r"\b(?!d\d|\d*d\d)[A-Za-z]{3,}\b")


def pick_action(state, suggestions, turn, max_turns, rng):
    hp_pct = state["hp"] / max(1, state["max_hp"])
    load = sum((state.get("backpack") or {}).get("res", {}).values())
    cap = (state.get("backpack") or {}).get("capacity", 8)
    low = [s.lower() for s in suggestions]

    if hp_pct <= 0.35 or load >= cap or turn >= int(max_turns * 0.8):
        for s, l in zip(suggestions, low):
            if any(w in l for w in EXIT_WORDS):
                return s, "план: уходить (мало HP / полный рюкзак / время)"
        return "Иду к ближайшему выходу из подземелья и выбираюсь наружу с добычей", "план: уходить (своя заявка)"
    if turn % 5 == 0:
        return rng.choice(CUSTOM), "свободная заявка (проверка free-text)"
    for s, l in zip(suggestions, low):
        if any(w in l for w in LOOT_WORDS):
            return s, "кнопка: добыча"
    for s, l in zip(suggestions, low):
        if any(w in l for w in FIGHT_WORDS):
            return s, "кнопка: бой"
    if suggestions:
        return rng.choice(suggestions), "кнопка: случайная"
    return rng.choice(CUSTOM), "свободная заявка (кнопок нет)"


def fmt_roll(r):
    kind = r.get("kind", "")
    s = f"`{r.get('reason','')}`: {r.get('count',1)}d{r.get('sides')}{r.get('modifier',0):+d} → {r.get('rolls')} = **{r.get('total')}**"
    if "dc" in r:
        s += f" против СЛ {r['dc']} — {'успех' if r.get('success') else 'провал'}"
    for flag in ("crit", "instant_kill", "echo_reroll", "fire_bonus", "targets"):
        if r.get(flag):
            s += f" [{flag}={r[flag]}]"
    return f"{s} _{kind}_" if kind else s


def play(client, dungeon, race, cls, max_turns, rng, out):
    name = f"Бот-{cls}"
    t0 = time.time()
    r = client.post("/api/run/new", json={"name": name, "race": race, "class": cls, "dungeon": dungeon})
    if r.status_code != 200:
        out.append(f"\n**Старт забега упал: {r.status_code} {r.text[:300]}**\n")
        return {"dungeon": dungeon, "error": True}
    data = r.json()
    lat = [time.time() - t0]
    rid = data["run_id"]
    m = {"dungeon": dungeon, "turns": 0, "rolls": 0, "checks": 0, "succ": 0, "dcs": [], "enemy_hits": 0,
         "arts": [], "latin": [], "narr_len": [], "unrolled_dmg": 0, "materials_in_inv": set(),
         "dups": set(), "errors": 0, "status": "active", "res_peak": {}, "hauled": {}, "no_suggest": 0,
         "custom_turns": 0}

    out.append(f"\n## Забег: {dungeon} · {race} {cls}\n")
    out.append(f"**Старт** ({lat[0]:.1f}с)\n\n{data['last']['narration']}\n")
    state, last = data["state"], data["last"]
    if last.get("scene_art"):
        m["arts"].append(last["scene_art"])

    for turn in range(1, max_turns + 1):
        action, why = pick_action(state, last.get("suggested_actions") or [], turn, max_turns, rng)
        if why.startswith("свободная"):
            m["custom_turns"] += 1
        hp_before = state["hp"]
        t1 = time.time()
        r = client.post(f"/api/run/{rid}/turn", json={"text": action})
        dt = time.time() - t1
        lat.append(dt)
        out.append(f"\n---\n### Ход {turn} ({dt:.1f}с) — {why}\n> **{action}**\n")
        if r.status_code != 200:
            m["errors"] += 1
            out.append(f"**ОШИБКА {r.status_code}:** {r.text[:400]}\n")
            if m["errors"] >= 3:
                break
            continue
        data = r.json()
        state, last = data["state"], data["last"]
        m["turns"] = turn
        narr = last.get("narration", "")
        m["narr_len"].append(len(narr))
        m["latin"] += [w for w in LATIN.findall(narr)]
        out.append(f"\n{narr}\n")
        rolls = last.get("rolls") or []
        for rr in rolls:
            m["rolls"] += 1
            out.append(f"- 🎲 {fmt_roll(rr)}")
            if "dc" in rr:
                m["checks"] += 1
                m["dcs"].append(rr["dc"])
                m["succ"] += 1 if rr.get("success") else 0
            if rr.get("kind") == "enemy_attack" and rr.get("success"):
                m["enemy_hits"] += 1
        if state["hp"] < hp_before and not any(rr.get("kind") in ("enemy_attack", "damage") or "dc" not in rr for rr in rolls):
            m["unrolled_dmg"] += 1
            out.append(f"- ⚠️ HP упало {hp_before}→{state['hp']} без броска урона")
        if last.get("scene_art"):
            m["arts"].append(last["scene_art"])
            out.append(f"- 🖼 арт: `{last['scene_art']}`")
        res = (state.get("backpack") or {}).get("res", {})
        for k, v in res.items():
            m["res_peak"][k] = max(m["res_peak"].get(k, 0), v)
        inv = state.get("inventory") or []
        low = [i.lower() for i in inv]
        m["dups"] |= {i for i in inv if low.count(i.lower()) > 1}
        m["materials_in_inv"] |= {i for i in inv if material_of(i)}
        if not last.get("suggested_actions"):
            m["no_suggest"] += 1
        out.append(f"- 📋 HP {state['hp']}/{state['max_hp']} · зол {state['gold']} · опыт {state['xp']} · "
                   f"глубина {state['depth']} · рюкзак {sum(res.values())}/{state['backpack']['capacity']} {res} · "
                   f"инвентарь {len(inv)}: {', '.join(inv)}")
        out.append(f"- кнопки: {' | '.join(last.get('suggested_actions') or [])}")
        if data["status"] != "active":
            m["status"] = data["status"]
            m["hauled"] = data.get("hauled") or {}
            out.append(f"\n**ФИНАЛ: {data['status']}** {data.get('death_cause') or ''} · вывезено: {m['hauled']}\n")
            break
    else:
        client.post(f"/api/run/{rid}/abandon")
        m["status"] = "лимит ходов бота"
    m["lat_avg"] = sum(lat) / len(lat)
    m["lat_max"] = max(lat)
    m["final"] = {"hp": state["hp"], "max_hp": state["max_hp"], "gold": state["gold"], "xp": state["xp"],
                  "level": state["level"], "depth": state["depth"]}
    return m


def summary(ms):
    lines = ["# Сводка плейтеста\n", "| метрика | " + " | ".join(m["dungeon"] for m in ms) + " |",
             "|---|" + "---|" * len(ms)]

    def row(title, f):
        lines.append(f"| {title} | " + " | ".join(str(f(m)) for m in ms) + " |")

    row("исход", lambda m: m.get("status"))
    row("ходов", lambda m: m.get("turns"))
    row("свободных заявок", lambda m: m.get("custom_turns"))
    row("бросков / проверок с СЛ", lambda m: f"{m.get('rolls')} / {m.get('checks')}")
    row("успех проверок", lambda m: f"{(m['succ'] * 100 // m['checks']) if m.get('checks') else 0}%")
    row("средняя СЛ", lambda m: f"{sum(m['dcs']) / len(m['dcs']):.1f}" if m.get("dcs") else "—")
    row("попаданий врагов", lambda m: m.get("enemy_hits"))
    row("урон без броска ⚠️", lambda m: m.get("unrolled_dmg"))
    row("ресурсов (пик в рюкзаке)", lambda m: sum(m.get("res_peak", {}).values()))
    row("вывезено в город", lambda m: m.get("hauled") or "—")
    row("артов показано", lambda m: f"{len(m.get('arts', []))} ({', '.join(sorted(set(m.get('arts', []))))})")
    row("латиница в тексте ⚠️", lambda m: ", ".join(sorted(set(m.get("latin", [])))) or "нет")
    row("дубли в инвентаре ⚠️", lambda m: ", ".join(m.get("dups", [])) or "нет")
    row("сырьё в инвентаре ⚠️", lambda m: ", ".join(m.get("materials_in_inv", [])) or "нет")
    row("ходов без кнопок", lambda m: m.get("no_suggest"))
    row("ошибок сервера", lambda m: m.get("errors"))
    row("средний текст, симв.", lambda m: sum(m["narr_len"]) // max(1, len(m["narr_len"])) if m.get("narr_len") else "—")
    row("ответ мастера, сек (сред/макс)", lambda m: f"{m.get('lat_avg', 0):.1f} / {m.get('lat_max', 0):.1f}")
    row("финал персонажа", lambda m: m.get("final"))
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dungeon", default="kar_mord", help="kar_mord | forest | monastery | all")
    ap.add_argument("--turns", type=int, default=25)
    ap.add_argument("--race", default="human")
    ap.add_argument("--class", dest="cls", default="fighter")
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()

    rng = random.Random(a.seed)
    client = TestClient(app)
    client.post("/api/city/prologue_done")
    dungeons = ["kar_mord", "forest", "monastery"] if a.dungeon == "all" else [a.dungeon]
    log, metrics = [], []
    from server.config import GM_PROVIDER, GM_MODEL, OPENAI_MODEL
    model = OPENAI_MODEL if GM_PROVIDER == "openai" else GM_MODEL
    for d in dungeons:
        # каждый забег — с чистого листа (слот искателя, лимиты)
        client.post("/api/admin/reset_account")
        client.post("/api/city/prologue_done")
        print(f"▶ играю {d} ...", flush=True)
        metrics.append(play(client, d, a.race, a.cls, a.turns, rng, log))
        print(f"  готово: {metrics[-1].get('status')}, ходов {metrics[-1].get('turns')}", flush=True)

    stamp = datetime.now().strftime("%m%d_%H%M")
    path = ROOT / f"playtest_{stamp}.md"
    head = (f"_Плейтест {datetime.now():%Y-%m-%d %H:%M} · мастер: {GM_PROVIDER} {model} · "
            f"корректор: {os.getenv('GM_PROOFREAD', '1')} · бот: {a.race} {a.cls}, до {a.turns} ходов_\n\n")
    path.write_text(head + summary(metrics) + "\n# Протокол\n" + "\n".join(log), encoding="utf-8")
    DB_FILE.unlink(missing_ok=True)
    print(f"\n✅ Протокол: {path.name} — скачай и пришли в чат на разбор")


if __name__ == "__main__":
    main()
