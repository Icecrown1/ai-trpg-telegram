# КАР-МОРД — AI-TRPG Telegram Mini App

Текстовая ролевая игра в духе ранних компьютерных RPG 90-х (Rogue, The Game of Dungeons).
Гейм-мастер — Claude (Haiku 4.5), броски кубиков — честный серверный RNG, эстетика —
оранжевый фосфорный CRT-терминал. Пермасмерть, один забег = 30–90 минут.

**Этап 0 (валидационный прототип):** один сеттинг (подземелье Кар-Морд), генерация
персонажа 3d6 (4 класса × 3 расы), гибрид «кнопки + свободный текст», прозрачные броски
d20, пошаговая боёвка, пермасмерть с мета-прогрессией, лимит 30 ходов/день.
Без платежей, картинок и мультиплеера — это следующие этапы.

## Стек

- **Фронт:** React + Vite, Telegram WebApp SDK (через `telegram-web-app.js`), CSS-ретро CRT
- **Бэк:** Python FastAPI, Claude API (tool use `roll_dice`, prompt caching, rolling summary)
- **БД:** SQLite локально → PostgreSQL на Replit одной переменной `DATABASE_URL`

## Структура

```
server/          FastAPI-бэкенд (источник истины по state)
  game/rules.py    расы, классы, генерация персонажа
  game/state.py    применение state_delta (модель предлагает — сервер решает)
  game/prompts.py  системный промпт + библия мира (в prompt cache)
  game/master.py   вызов Claude, tool loop с кубиками, суммаризация
  telegram_auth.py валидация initData (HMAC)
web/             React-фронт (оранжевый CRT-терминал)
start.sh         сборка фронта + запуск uvicorn (используется Replit)
```

## Запуск на Replit

1. **Import from GitHub** → этот репозиторий. Конфиг `.replit` уже на месте.
2. Вкладка **Secrets** → добавить:
   - `ANTHROPIC_API_KEY` — ключ из console.anthropic.com
   - `TELEGRAM_BOT_TOKEN` — токен бота из @BotFather
   - (для PostgreSQL) создать Replit PostgreSQL — `DATABASE_URL` появится сам;
     без него всё работает на SQLite.
3. **Run.** Первый запуск соберёт фронт (~1 мин).
4. В @BotFather: `/newapp` или `/setmenubutton` → указать URL реплита
   (`https://<название>.<юзер>.repl.co`). Открыть Mini App из бота.

## Локальная разработка

```bash
# бэкенд
pip install -r server/requirements.txt
ALLOW_DEV_AUTH=1 ANTHROPIC_API_KEY=sk-ant-... uvicorn server.main:app --reload

# фронт (отдельный терминал; /api проксируется на :8000)
cd web && npm install && npm run dev
```

`ALLOW_DEV_AUTH=1` позволяет тестировать в обычном браузере без Telegram —
никогда не включать в проде.

## Экономика хода

Дефолт — Haiku 4.5, статичный системный промпт и библия мира лежат в prompt cache
(−90% input), история сжимается rolling summary каждые 12 ходов, контекст — последние
10 ходов. Расчётная себестоимость ~0.5¢/ход; лимит free-tier — 30 ходов/день
(`FREE_TURNS_PER_DAY`).

## Дорожная карта

Этап 1 (MVP): +2 сеттинга, Telegram Stars (Free/Standard $5), рефералка, портреты героев
(gpt-image-1-mini, только ключевые сцены). Этап 2: мультиплеер по ссылке, лидерборды,
шаринг «карточек момента», Premium на Sonnet. Подробности — в концепт-документе проекта.
