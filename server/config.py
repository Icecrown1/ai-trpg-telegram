import os

# --- Core secrets (set in Replit Secrets / .env) ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# --- Models ---
GM_MODEL = os.getenv("GM_MODEL", "claude-haiku-4-5")
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", GM_MODEL)

# --- Database: sqlite locally, postgres on Replit via DATABASE_URL ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./game.db")
if DATABASE_URL.startswith("postgres://"):
    # SQLAlchemy needs the +psycopg2/postgresql scheme
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# --- Game limits / economics ---
FREE_TURNS_PER_DAY = int(os.getenv("FREE_TURNS_PER_DAY", "30"))
CONTEXT_RECENT_TURNS = int(os.getenv("CONTEXT_RECENT_TURNS", "10"))
SUMMARIZE_EVERY = int(os.getenv("SUMMARIZE_EVERY", "12"))
MAX_TOKENS_TURN = int(os.getenv("MAX_TOKENS_TURN", "1200"))

# --- Dev mode: browser access without Telegram ---
# ВРЕМЕННО включён по умолчанию на период отладки тестовой среды.
# ПЕРЕД ПУБЛИЧНЫМ ТЕСТОМ: задать ALLOW_DEV_AUTH=0 в Secrets (выключает при любом формате).
_dev_raw = os.getenv("ALLOW_DEV_AUTH", "1").strip().strip("\"'").lower()
ALLOW_DEV_AUTH = _dev_raw not in ("0", "false", "no", "off")
