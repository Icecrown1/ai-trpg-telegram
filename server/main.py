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
    return {"ok": True}


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
