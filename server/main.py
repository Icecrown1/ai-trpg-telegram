from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .db import Base, engine
from . import models  # noqa: F401 — register models before create_all
from .routers import game, stats, city

Base.metadata.create_all(bind=engine)

# мини-миграция для уже существующих баз (sqlite/postgres): добавить turns.scene_art
try:
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE turns ADD COLUMN scene_art VARCHAR(32)"))
except Exception:
    pass  # колонка уже есть

app = FastAPI(title="AI-TRPG Telegram Mini App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Mini App is served from the same origin in prod; dev needs this
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(game.router)
app.include_router(stats.router)
app.include_router(city.router)


@app.get("/api/health")
def health():
    from .config import (ALLOW_DEV_AUTH, GM_MODEL, GM_PROVIDER,
                         ANTHROPIC_API_KEY, OPENAI_API_KEY, TELEGRAM_BOT_TOKEN)
    from .routers.game import _server_version
    ver = _server_version()
    return {
        "ok": True,
        "version": ver,
        "dev_auth": ALLOW_DEV_AUTH,
        "gm_provider": GM_PROVIDER,
        "gm_model": GM_MODEL,
        "anthropic_key_set": bool(ANTHROPIC_API_KEY),
        "openai_key_set": bool(OPENAI_API_KEY),
        "telegram_token_set": bool(TELEGRAM_BOT_TOKEN),
        "frontend_built": (Path(__file__).resolve().parent.parent / "web" / "dist" / "index.html").exists(),
    }


@app.get("/api/gm-check")
def gm_check():
    """Живой тест связи с мастером: короткий реальный вызов API.
    Открой в браузере — увидишь либо ok, либо точную причину сбоя."""
    from .config import GM_MODEL, GM_PROVIDER
    from .game import master
    try:
        return {"ok": True, "provider": GM_PROVIDER, "model": GM_MODEL, "answer": master.ping()}
    except Exception as e:
        return {"ok": False, "provider": GM_PROVIDER, "model": GM_MODEL,
                "error_type": type(e).__name__, "error": str(e)[:600]}


# Serve the built frontend (web/dist), checked per-request: survives the case
# when the build finishes after the server has already started.
DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


@app.get("/{path:path}", include_in_schema=False)
async def spa(path: str):
    if path.startswith("api/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    candidate = (DIST / path).resolve()
    if path and candidate.is_file() and DIST in candidate.parents:
        return FileResponse(candidate)
    index = DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse(
        {"detail": "Фронтенд не собран. В Shell: bash start.sh — или дождись конца сборки и обнови страницу."},
        status_code=503,
    )
