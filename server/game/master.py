"""The AI game master: Claude with an honest server-side dice tool,
prompt caching and a rolling summary of older turns."""
import json
import re
import sys
import time

import anthropic

from ..config import (ANTHROPIC_API_KEY, OPENAI_API_KEY, GM_PROVIDER,
                      GM_MODEL, SUMMARY_MODEL, MAX_TOKENS_TURN)
from ..dice import roll
from .prompts import SYSTEM_PROMPT, WORLD_BIBLE, SUMMARY_PROMPT
from .resources import res_brief, backpack_load

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
            "stat": {
                "type": "string", "enum": ["STR", "DEX", "CON", "INT", "WIS", "CHA"],
                "description": "Какая характеристика персонажа проверяется. Сервер САМ добавит "
                               "модификатор из листа персонажа. Обязательно для d20-проверок.",
            },
            "modifier": {"type": "integer", "description": "ТОЛЬКО ситуативный бонус/штраф от -3 до +3 "
                               "(подходящий предмет, выгодная позиция). Не дублируй характеристику."},
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
    модель может добавить лишь ситуативные ±3."""
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
        stat_mod = (score - 10) // 2
        reason = f"{reason} ({_STAT_RU[stat]})" if reason else f"Проверка {_STAT_RU[stat]}"
    return roll(sides=sides, count=count, modifier=stat_mod + situational, reason=reason, dc=dc)


_SYSTEM_BLOCKS = [
    {"type": "text", "text": SYSTEM_PROMPT},
    {"type": "text", "text": WORLD_BIBLE, "cache_control": {"type": "ephemeral"}},
]


def _state_brief(state: dict) -> str:
    return json.dumps(
        {
            "имя": state["name"], "раса": state["race"], "класс": state["class"],
            "уровень": state["level"], "xp": state["xp"],
            "hp": f'{state["hp"]}/{state["max_hp"]}', "золото": state["gold"],
            "характеристики": state["stats"], "инвентарь": state["inventory"],
            "заклинания": state.get("spells", []),
            "локация": state["location"], "ярус": state["depth"],
            "сцена": state.get("scene", {}),
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


def _run_turn_openai(state: dict, summary: str, recent_turns: list, player_input: str) -> dict:
    intro = []
    if summary:
        intro.append(f"[СВОДКА ПРОШЛЫХ СОБЫТИЙ]\n{summary}")
    intro.append(f"[СОСТОЯНИЕ ПЕРСОНАЖА]\n{_state_brief(state)}")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + WORLD_BIBLE},
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
            kwargs["reasoning_effort"] = "low"
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
        return parsed

    return {"narration": "Подземелье замерло в нерешительности. Повтори действие.",
            "suggested_actions": [], "state_delta": {}, "scene_art": None,
            "game_over": False, "death_cause": None, "rolls": all_rolls}


def run_turn(state: dict, summary: str, recent_turns: list, player_input: str) -> dict:
    """One GM turn. Returns dict: narration, suggested_actions, state_delta,
    game_over, death_cause, rolls (list of dice results)."""
    if GM_PROVIDER == "openai":
        return _run_turn_openai(state, summary, recent_turns, player_input)
    messages = _build_messages(state, summary, recent_turns, player_input)
    all_rolls = []

    for _ in range(6):  # tool-use loop, hard-capped
        resp = _create(
            model=GM_MODEL,
            max_tokens=MAX_TOKENS_TURN,
            system=_SYSTEM_BLOCKS,
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


def opening_scene(state: dict) -> dict:
    """First narration of a fresh run."""
    return run_turn(
        state, "", [],
        "[СТАРТ ЗАБЕГА] Открывающая сцена, три части: "
        "1) Почему герой здесь — одна цепкая фраза о цели (золотая жила, долг, изгнание — сообразно классу). "
        "2) Снаряжение: перечисли предметы из инвентаря и заклинания (если есть) в тексте, "
        "чтобы игрок знал свой арсенал с первого хода. "
        "3) Вход в подземелье и первая развилка или деталь, требующая решения. "
        "Кубик не бросай — угроз в первой сцене нет.",
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
