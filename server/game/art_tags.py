"""Метки артов сцен — единый источник правды для сервера и промпта мастера."""

COMMON = {
    "stairs": "спуск на новую глубину", "skull": "смерть, останки", "goblin": "гоблин",
    "rat": "крыса", "undead": "нежить", "cultist": "культист", "merchant": "торговец",
    "chest": "сундук, находка", "altar": "алтарь, святилище", "potion": "зелье",
    "well": "колодец, шахта вниз", "torch": "факел, свет во тьме", "boss": "любой босс крупным планом",
    "spider": "паук", "ghost": "призрак, дух", "door": "запертая древняя дверь", "key": "ключ",
    "campfire": "чужой костёр, привал", "bones": "груда костей", "letter": "письмо, записка",
    "crown": "корона, королевская реликвия",
}

DUNGEON = {
    "gates": "дварфийские врата", "forge_dungeon": "горн Торина", "gold_vein": "жила живого золота",
    "lift": "грузовой подъёмник", "cavein": "обвал", "flooded_hall": "затопленный зал",
    "priest": "Пепельный Жрец",
    "forest": "тропа в чащу", "wolf": "волк", "rootwalker": "корневик", "witch_hut": "изба Осоки",
    "swamp_lights": "болотные огни", "hanging_oak": "Висельный дуб", "pastor": "Пастырь Корней",
    "scriptorium": "скрипторий", "bell": "колокольня", "cage": "клетка Финеуса",
    "stitched": "«очищенный», сшитая тварь", "candles": "шесть свечей Архимандрита",
    "archimandrite": "Архимандрит",
}


# Слабые модели иногда пишут метку по-русски — переводим в наш реестр
RU_ALIASES = {
    "ступени": "stairs", "лестница": "stairs", "спуск": "stairs", "череп": "skull", "гоблин": "goblin",
    "крыса": "rat", "крысы": "rat", "нежить": "undead", "культист": "cultist", "торговец": "merchant",
    "сундук": "chest", "алтарь": "altar", "зелье": "potion", "колодец": "well", "факел": "torch",
    "босс": "boss", "паук": "spider", "призрак": "ghost", "дух": "ghost", "дверь": "door", "ключ": "key",
    "костёр": "campfire", "костер": "campfire", "кости": "bones", "письмо": "letter", "записка": "letter",
    "корона": "crown", "врата": "gates", "ворота": "gates", "горн": "forge_dungeon", "кузня": "forge_dungeon",
    "жила": "gold_vein", "подъёмник": "lift", "подъемник": "lift", "обвал": "cavein", "лес": "forest",
    "волк": "wolf", "корневик": "rootwalker", "изба": "witch_hut", "огни": "swamp_lights",
    "дуб": "hanging_oak", "скрипторий": "scriptorium", "колокол": "bell", "колокольня": "bell",
    "клетка": "cage", "свечи": "candles",
}


def normalize(tag):
    """Метка от модели → метка реестра (или None). Регистр, пробелы и русские синонимы прощаем."""
    if not tag or not isinstance(tag, str):
        return None
    t = tag.strip().lower().replace(" ", "_")
    if t in COMMON or t in DUNGEON:
        return t
    return RU_ALIASES.get(t.replace("_", " "))


def guide(dungeon_tags) -> str:
    own = ", ".join(f"{t} ({DUNGEON.get(t, t)})" for t in sorted(dungeon_tags or []))
    common = ", ".join(f"{t} ({d})" for t, d in COMMON.items())
    return (
        "МЕТКИ АРТОВ (поле scene_art). Ставь щедро: примерно каждые 2-3 хода и всегда при входе в новое "
        "место, появлении существа или NPC, находке, бое, ритуале. null — только если в ходе нет ничего "
        "зримого. Повтор той же метки в ближайшие ходы сервер погасит сам.\n"
        f"Метки ЭТОГО подземелья: {own}.\n"
        f"Общие метки: {common}.\n"
        "Метки других подземелий запрещены — их нет в этом мире."
    )
