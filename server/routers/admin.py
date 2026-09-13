"""Тестовая админка: сбросы для отладки. Доступ: dev-режим или ADMIN_TG_IDS."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User, City, Seeker, Run, Turn
from ..telegram_auth import get_tg_user
from ..config import ADMIN_TG_IDS, ALLOW_DEV_AUTH

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_admin(tg) -> None:
    if ALLOW_DEV_AUTH or int(tg["id"]) in ADMIN_TG_IDS:
        return
    raise HTTPException(403, "Не для смертных")


def _user(db: Session, tg) -> User:
    user = db.query(User).filter(User.tg_id == tg["id"]).first()
    if not user:
        raise HTTPException(404, "Сначала зайди в игру")
    return user


@router.get("/check")
def check(tg=Depends(get_tg_user)):
    return {"admin": ALLOW_DEV_AUTH or int(tg["id"]) in ADMIN_TG_IDS}


@router.post("/reset_cooldown")
def reset_cooldown(tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    _require_admin(tg)
    user = _user(db, tg)
    user.run_stamps = []
    db.commit()
    return {"ok": True}


@router.post("/reset_prologue")
def reset_prologue(tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    _require_admin(tg)
    user = _user(db, tg)
    city = db.query(City).filter(City.user_id == user.id).first()
    if city:
        flags = dict(city.flags or {})
        flags.pop("prologue_done", None)
        city.flags = flags
        db.commit()
    return {"ok": True}


@router.post("/reset_account")
def reset_account(tg=Depends(get_tg_user), db: Session = Depends(get_db)):
    """Полный сброс: город, искатели, забеги, кулдауны. Для чистого прогона онбординга."""
    _require_admin(tg)
    user = _user(db, tg)
    run_ids = [r.id for r in db.query(Run.id).filter(Run.user_id == user.id).all()]
    if run_ids:
        db.query(Turn).filter(Turn.run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(Run).filter(Run.id.in_(run_ids)).delete(synchronize_session=False)
    db.query(Seeker).filter(Seeker.user_id == user.id).delete(synchronize_session=False)
    db.query(City).filter(City.user_id == user.id).delete(synchronize_session=False)
    user.run_stamps = []
    user.total_runs = 0
    user.deepest_level = 1
    user.best_gold = 0
    db.commit()
    return {"ok": True}
