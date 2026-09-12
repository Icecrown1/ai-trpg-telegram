"""Каталог Башни мага: расходники Финеуса. Кладутся в инвентарь искателя."""

MAGIC = {
    "scroll_heal": {
        "name": "Свиток малого исцеления", "tower": 1,
        "cost": {"cloth": 2}, "gold": 15,
        "effect": "при чтении: hp +2d4 (мастер бросает и применяет)",
    },
    "wand_light": {
        "name": "Жезл немеркнущего света", "tower": 1,
        "cost": {"wood": 1, "cloth": 1}, "gold": 10,
        "effect": "ровный свет без факелов; в темноте снимает штрафы на внимательность",
    },
    "scroll_stoneskin": {
        "name": "Свиток каменной кожи", "tower": 2,
        "cost": {"stone": 2, "ash_essence": 1}, "gold": 40,
        "effect": "при чтении: защита +2 на 3 хода (сервер применит сам)",
    },
    "scroll_blade": {
        "name": "Свиток призрачного клинка", "tower": 2,
        "cost": {"ash_essence": 1, "cloth": 2}, "gold": 50,
        "effect": "призывает клинок-союзник на один бой: атакует как 1d20+2, урон 1d6",
    },
    "scroll_lastbreath": {
        "name": "Свиток последнего вздоха", "tower": 3,
        "cost": {"soul_shard": 1, "cloth": 2}, "gold": 120,
        "effect": "сгорает сам в момент смерти носителя, оставляя его на 1 HP (сервер гарантирует)",
    },
    "wand_fire": {
        "name": "Жезл огненной плети (3 заряда)", "tower": 3,
        "cost": {"ash_essence": 2, "soul_shard": 1}, "gold": 150,
        "effect": "удар огнём 2d6, игнорирует завесы и нимбы; 3 заряда, следи за ними и убери жезл, когда пусты",
    },
}

LASTBREATH_NAME = MAGIC["scroll_lastbreath"]["name"]
STONESKIN_NAME = MAGIC["scroll_stoneskin"]["name"]
