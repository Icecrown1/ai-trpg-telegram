"""Shared player strategies for single-run and batch playtests."""

from server.game.resources import backpack_load, stack_of

PLAYER_PROMPT = (
    "Ты — опытный игрок в настольные RPG, играешь в текстовую extraction-RPG на русском. Цель забега: "
    "добыть ресурсы для своего города, найти ценности, выжить и выбраться через точку выхода. Играй как живой "
    "человек: используй окружение, хитрости, разговоры с NPC, засады, торг; иногда рискуй ради добычи, но береги "
    "жизнь. Кнопки — только подсказки, чаще пиши свою заявку. Отвечай ОДНОЙ заявкой от первого лица, 1-2 "
    "предложения, без кавычек и пояснений."
)

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


def pick_action(state, suggestions, turn, max_turns, rng):
    hp_pct = state["hp"] / max(1, state["max_hp"])
    backpack = state.get("backpack") or {}
    load = backpack_load(backpack.get("res") or {}, stack_of(backpack))
    cap = backpack.get("capacity", 8)
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
