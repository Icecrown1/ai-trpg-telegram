from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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


# Serve the built frontend (web/dist) if present — single deployment on Replit
dist = Path(__file__).resolve().parent.parent / "web" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="static")
