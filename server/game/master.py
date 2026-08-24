"""The AI game master: Claude with an honest server-side dice tool,
prompt caching and a rolling summary of older turns."""
import json
import re
import sys

import anthropic

from ..config import ANTHROPIC_API_KEY, GM_MODEL, SUMMARY_MODEL, MAX_TOKENS_TURN
from ..dice import roll
from .prompts import SYSTEM_PROMPT, WORLD_BIBLE, SUMMARY_PROMPT

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

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
            "modifier": {"type": "integer", "description": "Модификатор к сумме"},
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


def run_turn(state: dict, summary: str, recent_turns: list, player_input: str) -> dict:
    """One GM turn. Returns dict: narration, suggested_actions, state_delta,
    game_over, death_cause, rolls (list of dice results)."""
    messages = _build_messages(state, summary, recent_turns, player_input)
    all_rolls = []

    for _ in range(6):  # tool-use loop, hard-capped
        resp = client.messages.create(
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
                    sides = block.input.get("sides", 20)
                    count = block.input.get("count", 1)
                    dc = block.input.get("dc")
                    # Принуждение: одиночный d20 — это всегда проверка, без СЛ не бывает.
                    if dc is None and sides == 20 and count == 1:
                        dc = 12
                    outcome = roll(
                        sides=sides,
                        count=count,
                        modifier=block.input.get("modifier", 0),
                        reason=block.input.get("reason", ""),
                        dc=dc,
                    )
                    all_rolls.append(outcome)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(outcome, ensure_ascii=False),
                    })
            messages.append({"role": "user", "content": results})
            continue

        text = "".join(b.text for b in resp.content if b.type == "text")
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

        if not parsed.get("suggested_actions"):
            parsed["suggested_actions"] = ["Осмотреться", "Идти дальше", "Прислушаться"]
        parsed.setdefault("state_delta", {})
        parsed.setdefault("scene_art", None)
        parsed.setdefault("game_over", False)
        parsed.setdefault("death_cause", None)
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
    resp = client.messages.create(
        model=SUMMARY_MODEL,
        max_tokens=600,
        system=SUMMARY_PROMPT,
        messages=[{"role": "user", "content": "\n\n".join(lines)}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()
