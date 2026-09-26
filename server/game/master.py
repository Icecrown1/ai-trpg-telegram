"""The AI game master: Claude with an honest server-side dice tool,
prompt caching and a rolling summary of older turns."""
import json
import re
import sys
import time

import anthropic

from ..config import (ANTHROPIC_API_KEY, OPENAI_API_KEY, GM_PROVIDER,
                      GM_MODEL, SUMMARY_MODEL, MAX_TOKENS_TURN,
                      GM_PROOFREAD, OPENAI_REASONING)
from ..dice import roll
from .prompts import SYSTEM_PROMPT, SUMMARY_PROMPT
from .dungeons import get_dungeon, DEFAULT_DUNGEON
from .resources import res_brief, backpack_load
from .gear import defense
from .talents import TALENTS, stat_check_bonus, attack_bonus as talent_attack_bonus
from .artifacts import ARTIFACTS as _ART, owned as _owned_art
from . import bestiary as _bestiary

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_openai = None


def _openai_client():
    global _openai
    if _openai is None:
        import openai
        _openai = openai.OpenAI(api_key=OPENAI_API_KEY)
    return _openai

_TRANSIENT = (429, 500, 502, 503, 529)


def _create(**kwargs):
    """Вызов API с автоповтором на временных сбоях (перегрузка, сеть)."""
    last = None
    for attempt in range(3):
        try:
            return client.messages.create(**kwargs)
        except anthropic.APIConnectionError as e:
            last = e
        except anthropic.APIStatusError as e:
            if e.status_code not in _TRANSIENT:
                raise
            last = e
        wait = 1.5 * (attempt + 1)
        print(f"[GM RETRY] attempt={attempt+1} err={type(last).__name__}: {last}", file=sys.stderr)
        time.sleep(wait)
    raise last

ROLL_DICE_TOOL = {
    "name": "roll_dice",
    "description": (
        "Честный бросок кубиков на сервере. Вызывай для любого действия с "
        "неопределённым исходом. Результат обязателен к использованию как есть."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sides": {"type": "integer", "description": "Граней у кубика (например 20, 6)"},
            "count": {"type": "integer", "description": "Сколько кубиков, по умолчанию 1"},
            "kind": {
                "type": "string", "enum": ["check", "player_attack", "enemy_attack", "damage"],
                "description": "Тип броска: player_attack (атака игрока, сервер добавит бонус оружия), "
                               "enemy_attack (по игроку, сервер подставит СЛ=защите), damage (урон), check.",
            },
            "stat": {
                "type": "string", "enum": ["STR", "DEX", "CON", "INT", "WIS", "CHA"],
                "description": "Какая характеристика персонажа проверяется. Сервер САМ добавит "
                               "модификатор из листа персонажа. Обязательно для d20-проверок.",
            },
            "modifier": {"type": "integer", "description": "ТОЛЬКО ситуативный бонус/штраф от -3 до +3 "
                               "(подходящий предмет, выгодная позиция). Не дублируй характеристику."},
            "targets": {"type": "integer", "description": "Для player_attack по нескольким целям: сколько "
                               "врагов накрывает удар (1-3). Сервер сам поднимет СЛ за каждую цель сверх первой."},
            "target": {"type": "string", "description": "Для player_attack: id существа из бестиария, "
                       "по которому бьёт игрок (при ударе по нескольким — самое защищённое). Сервер сам поставит КД."},
            "attacker": {"type": "string", "description": "Для enemy_attack: id атакующего существа из бестиария. "
                         "Сервер сам добавит его бонус атаки."},
            "advantage_die": {"type": "integer", "enum": [3, 6],
                              "description": "РЕАЛЬНОЕ преимущество (засада, подготовленная позиция, "
                               "слабость врага использована): сервер бросит дополнительный d3 или d6 и "
                               "прибавит к результату. Не для смутных заявок."},
            "reason": {"type": "string", "description": "Что проверяется, по-русски, коротко"},
            "dc": {
                "type": "integer",
                "description": "Сложность проверки (DC) для d20-проверок. Обязательно для проверок "
                               "успех/провал — игрок видит её. Не указывай для бросков урона.",
            },
        },
        "required": ["sides", "reason"],
    },
}

_STAT_RU = {"STR": "СИЛ", "DEX": "ЛОВ", "CON": "ВЫН", "INT": "ИНТ", "WIS": "МДР", "CHA": "ХАР"}


def _exec_roll(args: dict, state: dict) -> dict:
    """Выполнение броска: модификатор характеристики берётся из листа персонажа,
    модель может добавить лишь ситуативные ±3. Сервер сам считает: цели (СЛ+3 за
    каждую сверх первой), преимущество (доп. кубик d3/d6), криты 16-20 и мгновенное
    убийство (чистая 20 против СЛ 20)."""
    sides = args.get("sides", 20)
    count = args.get("count", 1)
    dc = args.get("dc")
    if dc is None and sides == 20 and count == 1:
        dc = 12
    situational = 0
    try:
        situational = max(-3, min(3, int(args.get("modifier", 0) or 0)))
    except (TypeError, ValueError):
        pass
    stat = args.get("stat")
    stat_mod = 0
    reason = args.get("reason", "")
    if stat in _STAT_RU:
        score = int((state.get("stats") or {}).get(stat, 10))
        stat_mod = (score - 10) // 2 + stat_check_bonus(state.get("talents"), stat)
        reason = f"{reason} ({_STAT_RU[stat]})" if reason else f"Проверка {_STAT_RU[stat]}"

    kind = args.get("kind") or "check"
    weapon_mod = 0
    targets = 1
    if kind == "enemy_attack":
        dc = defense(state)  # СЛ атак по игроку диктует сервер: броня работает всегда
        stat_mod = 0          # характеристики игрока не помогают врагу попасть
        foe = _bestiary.get(args.get("attacker"))
        if foe:
            weapon_mod = int(foe["atk"])  # бонус атаки существа из бестиария
            reason = f"{reason} [{foe['name']}, атака +{foe['atk']}]"
    elif kind == "player_attack":
        foe = _bestiary.get(args.get("target"))
        if foe:
            dc = int(foe["ac"]) + _bestiary.depth_bonus(state.get("depth", 1), foe)
            reason = f"{reason} [{foe['name']}, КД {dc}]"
        weapon = (state.get("equipment") or {}).get("weapon") or {}
        weapon_mod = int(weapon.get("atk", 0)) + talent_attack_bonus(state.get("talents"))
        if weapon_mod:
            reason = f"{reason} [{weapon.get('name', 'оружие')} +{weapon_mod}]"
        try:
            targets = max(1, min(3, int(args.get("targets", 1) or 1)))
        except (TypeError, ValueError):
            targets = 1
        if targets > 1 and dc is not None:
            dc = int(dc) + 3 * (targets - 1)  # размашистый удар: одна проверка, СЛ выше
            reason = f"{reason} [по {targets} целям, СЛ +{3 * (targets - 1)}]"
    elif kind == "damage":
        dc = None

    adv_bonus = 0
    adv_die = args.get("advantage_die")
    if adv_die in (3, 6) and kind != "damage":
        import secrets as _s
        adv_bonus = _s.randbelow(int(adv_die)) + 1
        reason = f"{reason} [преимущество 1d{adv_die}: +{adv_bonus}]"

    result = roll(sides=sides, count=count,
                  modifier=stat_mod + situational + weapon_mod + adv_bonus,
                  reason=reason, dc=dc)

    from .artifacts import owned as _owned
    have = _owned(state)
    # Эхо-раковина: раз за забег перебрасывает первый проваленный бросок игрока
    if ("echo_shell" in have and kind in ("check", "player_attack") and sides == 20
            and result.get("success") is False
            and not (state.get("flags") or {}).get("echo_used")):
        first = result["rolls"][0]
        result = roll(sides=sides, count=count,
                      modifier=stat_mod + situational + weapon_mod + adv_bonus,
                      reason=f"{reason} [эхо-раковина: переброс, было {first}]", dc=dc)
        result["echo_reroll"] = True
        state.setdefault("flags", {})["echo_used"] = True  # сохранится с состоянием хода

    # Клык из глубин: при попадании сервер сам бросает огненный 1d4
    if "depth_fang" in have and kind == "player_attack" and result.get("success"):
        import secrets as _s2
        fire = _s2.randbelow(4) + 1
        result["fire_bonus"] = fire
        result["reason"] = f"{result['reason']} [клык: +{fire} огнём к урону]"

    # Криты: сервер помечает, мастер обязан отыграть
    if kind == "player_attack" and sides == 20 and result.get("count", 1) == 1:
        natural = result["rolls"][0]
        hit = result.get("success", result.get("dc") is None)
        if natural == 20 and result.get("dc") is not None and int(result["dc"]) >= 20 and hit:
            result["instant_kill"] = True
        elif natural >= 16 and hit:
            result["crit"] = True
    if targets > 1:
        result["targets"] = targets
    return result


def _system_blocks(dungeon_id: str) -> list:
    bible = get_dungeon(dungeon_id)["bible"] + "\n\n" + _bestiary.prompt_block(dungeon_id)
    return [
        {"type": "text", "text": SYSTEM_PROMPT},
        {"type": "text", "text": bible, "cache_control": {"type": "ephemeral"}},
    ]


def _state_brief(state: dict) -> str:
    return json.dumps(
        {
            "имя": state["name"], "раса": state["race"], "класс": state["class"],
            "уровень": state["level"], "xp": state["xp"],
            "hp": f'{state["hp"]}/{state["max_hp"]}', "золото": state["gold"],
            "характеристики": state["stats"], "инвентарь": state["inventory"],
            "заклинания": state.get("spells", []),
            "таланты": [
                {"название": TALENTS[t]["name"], "суть": TALENTS[t]["desc"]}
                for t in state.get("talents", []) if t in TALENTS
            ],
            "артефакты": [
                {"название": _ART[a]["name"], "правило": _ART[a]["rule"]}
                for a in sorted(_owned_art(state))
            ],
            "локация": state["location"], "ярус": state["depth"],
            "сцена": state.get("scene", {}),
            "партия": [
                {"имя": m.get("name"), "класс": m.get("cls"),
                 "hp": f'{m.get("hp")}/{m.get("max_hp")}', "преданность": m.get("loyalty", 0)}
                for m in state.get("party", [])
            ],
            "защита": defense(state),
            "оружие": ((state.get("equipment") or {}).get("weapon") or {}).get("name")
                      and {**(state.get("equipment") or {}).get("weapon", {})} or None,
            "броня": ((state.get("equipment") or {}).get("armor") or {}).get("name")
                     and {**(state.get("equipment") or {}).get("armor", {})} or None,
            "рюкзак": {
                "занято": backpack_load((state.get("backpack") or {}).get("res")),
                "вместимость": (state.get("backpack") or {}).get("capacity", 8),
                "ресурсы": res_brief((state.get("backpack") or {}).get("res")),
            },
            "флаги": state.get("flags", {}),
        },
        ensure_ascii=False,
    )


def _build_messages(state: dict, summary: str, recent_turns: list, player_input: str) -> list:
    messages = []
    intro = []
    if summary:
        intro.append(f"[СВОДКА ПРОШЛЫХ СОБЫТИЙ]\n{summary}")
    intro.append(f"[СОСТОЯНИЕ ПЕРСОНАЖА]\n{_state_brief(state)}")
    messages.append({"role": "user", "content": "\n\n".join(intro)})
    messages.append({"role": "assistant", "content": "Принято. Жду действий игрока."})

    for t in recent_turns:
        messages.append({"role": "user", "content": t.player_input})
        messages.append({"role": "assistant", "content": t.narration})

    messages.append({"role": "user", "content": player_input})
    return messages


def _clean_narration(text: str) -> str:
    """Страховка от markdown и мусора в тексте хода."""
    text = re.sub(r"```[a-z]*\n?", "", text)          # code fences
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)     # **жирный**
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.M)    # заголовки
    return text.strip()


def _extract_json(text: str) -> dict:
    """Модель обязана вернуть голый JSON, но страхуемся от любого мусора вокруг:
    сканируем все '{' и берём ПОСЛЕДНИЙ валидный объект с ключом narration."""
    stripped = re.sub(r"```(?:json)?", "", text)
    decoder = json.JSONDecoder()
    found = None
    for i, ch in enumerate(stripped):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(stripped[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "narration" in obj:
            found = obj  # последний валидный побеждает (проза до него отбрасывается)
    if found is not None:
        found["narration"] = _clean_narration(str(found.get("narration", "")))
        return found
    # совсем не JSON — отдаём вычищенный текст как повествование, игра не встаёт
    return {"narration": _clean_narration(stripped) or "…Тьма молчит. Попробуй ещё раз.",
            "suggested_actions": []}


_PROOFREAD_PROMPT = (
    "Ты — корректор русского художественного текста. Исправь ТОЛЬКО язык:\n"
    "- несуществующие и исковерканные слова замени существующими по смыслу\n"
    "- почини согласование рода, числа, падежа и лица («ты пятишься», не «ты пятится»)\n"
    "- слова латиницей переведи на русский (кроме обозначений кубиков вроде d20, 1d6)\n"
    "- обрубленные идиомы допиши или замени простыми словами\n"
    "ЗАПРЕЩЕНО: менять события, имена, названия, числа, реплики по смыслу, добавлять или "
    "убирать предложения, менять стиль. Если текст уже чист — верни его без изменений.\n"
    "Верни ТОЛЬКО исправленный текст, без комментариев и кавычек."
)


def _proofread(narration: str) -> str:
    """Быстрый второй проход: чинит язык, не трогая содержание. Ошибся — вернём оригинал."""
    try:
        kwargs = dict(
            model=GM_MODEL,
            max_completion_tokens=MAX_TOKENS_TURN,
            messages=[{"role": "system", "content": _PROOFREAD_PROMPT},
                      {"role": "user", "content": narration}],
        )
        if GM_MODEL.startswith(("gpt-5", "o1", "o3", "o4")):
            kwargs["reasoning_effort"] = "minimal"
        resp = _openai_create(**kwargs)
        fixed = (resp.choices[0].message.content or "").strip()
        # страховка: корректор не должен ни съесть текст, ни раздуть его
        if len(fixed) >= len(narration) * 0.6 and len(fixed) <= len(narration) * 1.5:
            return fixed
    except Exception as e:
        print(f"[PROOFREAD SKIP] {type(e).__name__}: {e}", file=sys.stderr)
    return narration


OPENAI_TOOL = {
    "type": "function",
    "function": {
        "name": "roll_dice",
        "description": ROLL_DICE_TOOL["description"],
        "parameters": ROLL_DICE_TOOL["input_schema"],
    },
}


def _openai_create(**kwargs):
    import openai
    last = None
    for attempt in range(3):
        try:
            return _openai_client().chat.completions.create(**kwargs)
        except openai.APIConnectionError as e:
            last = e
        except openai.APIStatusError as e:
            if e.status_code not in _TRANSIENT:
                raise
            last = e
        print(f"[GM RETRY openai] attempt={attempt+1} err={type(last).__name__}: {last}", file=sys.stderr)
        time.sleep(1.5 * (attempt + 1))
    raise last


def _run_turn_openai(state: dict, summary: str, recent_turns: list, player_input: str,
                     dungeon_id: str = DEFAULT_DUNGEON) -> dict:
    intro = []
    if summary:
        intro.append(f"[СВОДКА ПРОШЛЫХ СОБЫТИЙ]\n{summary}")
    intro.append(f"[СОСТОЯНИЕ ПЕРСОНАЖА]\n{_state_brief(state)}")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + get_dungeon(dungeon_id)["bible"]
                                      + "\n\n" + _bestiary.prompt_block(dungeon_id)},
        {"role": "user", "content": "\n\n".join(intro)},
        {"role": "assistant", "content": "Принято. Жду действий игрока."},
    ]
    for t in recent_turns:
        messages.append({"role": "user", "content": t.player_input})
        messages.append({"role": "assistant", "content": t.narration})
    messages.append({"role": "user", "content": player_input})

    all_rolls = []
    for _ in range(6):
        kwargs = dict(
            model=GM_MODEL,
            # у reasoning-моделей токены размышлений едят тот же лимит — даём запас
            max_completion_tokens=MAX_TOKENS_TURN * 2,
            tools=[OPENAI_TOOL],
            messages=messages,
        )
        if GM_MODEL.startswith(("gpt-5", "o1", "o3", "o4")):
            kwargs["reasoning_effort"] = OPENAI_REASONING
        resp = _openai_create(**kwargs)
        msg = resp.choices[0].message

        if msg.tool_calls:
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ],
            })
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                outcome = _exec_roll(args, state)
                all_rolls.append(outcome)
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": json.dumps(outcome, ensure_ascii=False)})
            continue

        text = msg.content or ""
        if not text.strip():
            print(f"[GM RAW EMPTY openai] finish={resp.choices[0].finish_reason} (no content)",
                  file=sys.stderr)
            messages.append({"role": "user", "content":
                "[СБОЙ ФОРМАТА] Ответ пришёл пустым. Заверши ход ЗАНОВО: полный JSON, "
                "narration с исходом всех уже брошенных кубиков, state_delta с уроном, "
                "3-4 suggested_actions. Только JSON."})
            continue
        parsed = _extract_json(text)
        narration = str(parsed.get("narration", "")).strip()
        if len(narration) < 15:
            print(f"[GM RAW EMPTY openai] finish={resp.choices[0].finish_reason} text={text[:400]!r}",
                  file=sys.stderr)
            messages.append({"role": "assistant", "content": text or "…"})
            messages.append({"role": "user", "content":
                "[СБОЙ ФОРМАТА] Твой прошлый ответ был пуст или оборван. Повтори ход ЗАНОВО: "
                "полный JSON, narration 2-4 абзаца, 3-4 suggested_actions. Только JSON."})
            continue
        parsed.setdefault("suggested_actions", [])
        parsed.setdefault("state_delta", {})
        parsed.setdefault("scene_art", None)
        parsed.setdefault("game_over", False)
        parsed.setdefault("death_cause", None)
        parsed.setdefault("extracted", False)
        parsed["rolls"] = all_rolls
        if GM_PROOFREAD:
            parsed["narration"] = _proofread(str(parsed["narration"]))
        return parsed

    return {"narration": "Подземелье замерло в нерешительности. Повтори действие.",
            "suggested_actions": [], "state_delta": {}, "scene_art": None,
            "game_over": False, "death_cause": None, "rolls": all_rolls}


def run_turn(state: dict, summary: str, recent_turns: list, player_input: str,
             dungeon_id: str = DEFAULT_DUNGEON) -> dict:
    """One GM turn. Returns dict: narration, suggested_actions, state_delta,
    game_over, death_cause, rolls (list of dice results)."""
    if GM_PROVIDER == "openai":
        return _run_turn_openai(state, summary, recent_turns, player_input, dungeon_id)
    messages = _build_messages(state, summary, recent_turns, player_input)
    all_rolls = []

    for _ in range(6):  # tool-use loop, hard-capped
        resp = _create(
            model=GM_MODEL,
            max_tokens=MAX_TOKENS_TURN,
            system=_system_blocks(dungeon_id),
            tools=[ROLL_DICE_TOOL],
            messages=messages,
        )

        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if block.type == "tool_use" and block.name == "roll_dice":
                    outcome = _exec_roll(block.input, state)
                    all_rolls.append(outcome)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(outcome, ensure_ascii=False),
                    })
            messages.append({"role": "user", "content": results})
            continue

        text = "".join(b.text for b in resp.content if b.type == "text")
        if not text.strip():
            print(f"[GM RAW EMPTY] stop={resp.stop_reason} (no content)", file=sys.stderr)
            messages.append({"role": "assistant", "content": "…"})
            messages.append({"role": "user", "content":
                "[СБОЙ ФОРМАТА] Ответ пришёл пустым. Заверши ход ЗАНОВО: полный JSON, "
                "narration с исходом всех уже брошенных кубиков, state_delta с уроном, "
                "3-4 suggested_actions. Только JSON."})
            continue
        parsed = _extract_json(text)
        narration = str(parsed.get("narration", "")).strip()

        # пустой/оборванный ответ (лимит токенов, сбой формата) — один повтор с пинком
        if len(narration) < 15:
            print(f"[GM RAW EMPTY] stop={resp.stop_reason} text={text[:400]!r}", file=sys.stderr)
            messages.append({"role": "assistant", "content": text or "…"})
            messages.append({"role": "user", "content":
                "[СБОЙ ФОРМАТА] Твой прошлый ответ был пуст или оборван. Повтори ход ЗАНОВО: "
                "полный JSON, narration 2-4 абзаца, 3-4 suggested_actions. Только JSON."})
            continue

        parsed.setdefault("suggested_actions", [])
        parsed.setdefault("state_delta", {})
        parsed.setdefault("scene_art", None)
        parsed.setdefault("game_over", False)
        parsed.setdefault("death_cause", None)
        parsed.setdefault("extracted", False)
        parsed["rolls"] = all_rolls
        return parsed

    return {
        "narration": "Подземелье замерло в нерешительности. Повтори действие.",
        "suggested_actions": [], "state_delta": {}, "game_over": False,
        "death_cause": None, "rolls": all_rolls,
    }


def opening_scene(state: dict, dungeon_id: str = DEFAULT_DUNGEON) -> dict:
    """First narration of a fresh run."""
    return run_turn(
        state, "", [],
        "[СТАРТ ЗАБЕГА] Открывающая сцена, три части: "
        "1) Почему герой здесь — одна цепкая фраза о цели (золотая жила, долг, изгнание — сообразно классу). "
        "2) Снаряжение: перечисли предметы из инвентаря и заклинания (если есть) в тексте, "
        "чтобы игрок знал свой арсенал с первого хода. "
        "3) Вход в подземелье и первая развилка или деталь, требующая решения. "
        "Кубик не бросай — угроз в первой сцене нет.",
        dungeon_id=dungeon_id,
    )


def summarize(old_summary: str, turns: list) -> str:
    """Fold older turns into the rolling summary."""
    lines = []
    if old_summary:
        lines.append(f"[ПРЕДЫДУЩАЯ СВОДКА]\n{old_summary}")
    for t in turns:
        lines.append(f"Игрок: {t.player_input}\nМастер: {t.narration}")
    if GM_PROVIDER == "openai":
        resp = _openai_create(
            model=SUMMARY_MODEL, max_completion_tokens=600,
            messages=[{"role": "system", "content": SUMMARY_PROMPT},
                      {"role": "user", "content": "\n\n".join(lines)}],
        )
        return (resp.choices[0].message.content or "").strip()
    resp = _create(
        model=SUMMARY_MODEL,
        max_tokens=600,
        system=SUMMARY_PROMPT,
        messages=[{"role": "user", "content": "\n\n".join(lines)}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def ping() -> str:
    """Короткий живой вызов текущего провайдера — для /api/gm-check."""
    if GM_PROVIDER == "openai":
        resp = _openai_create(model=GM_MODEL, max_completion_tokens=16,
                              messages=[{"role": "user", "content": "Ответь одним словом: жив"}])
        return (resp.choices[0].message.content or "").strip()
    resp = _create(model=GM_MODEL, max_tokens=16,
                   messages=[{"role": "user", "content": "Ответь одним словом: жив"}])
    return "".join(b.text for b in resp.content if b.type == "text").strip()
