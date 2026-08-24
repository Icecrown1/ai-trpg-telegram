from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .db import Base, engine
from . import models  # noqa: F401 — register models before create_all
from .routers import game

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI-TRPG Telegram Mini App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Mini App is served from the same origin in prod; dev needs this
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(game.router)


@app.get("/api/health")
def health():
    import subprocess
    from .config import ALLOW_DEV_AUTH, GM_MODEL, ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN
    try:
        ver = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL,
            cwd=Path(__file__).resolve().parent,
        ).strip()
    except Exception:
        ver = "unknown"
    return {
        "ok": True,
        "version": ver,
        "dev_auth": ALLOW_DEV_AUTH,
        "gm_model": GM_MODEL,
        "anthropic_key_set": bool(ANTHROPIC_API_KEY),
        "telegram_token_set": bool(TELEGRAM_BOT_TOKEN),
        "frontend_built": (Path(__file__).resolve().parent.parent / "web" / "dist" / "index.html").exists(),
    }


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
