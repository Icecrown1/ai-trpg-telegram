"""Aggregate playtest analytics: /api/stats
Открытый JSON без персональных данных — только цифры для решений по геймплею."""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User, Run, Turn

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    total_users = db.query(func.count(User.id)).scalar() or 0
    runs_by_status = dict(
        db.query(Run.status, func.count(Run.id)).group_by(Run.status).all()
    )
    total_runs = sum(runs_by_status.values())

    # длина забегов (в ходах) по завершённым
    finished = db.query(Run.turn_count).filter(Run.status.in_(["dead", "abandoned"])).all()
    lens = sorted(r[0] for r in finished)
    avg_len = round(sum(lens) / len(lens), 1) if lens else 0
    med_len = lens[len(lens) // 2] if lens else 0

    # где умирают: глубина и ход смерти
    dead = db.query(Run).filter(Run.status == "dead").all()
    death_depths = {}
    death_turns = []
    death_causes = []
    for r in dead:
        d = (r.state or {}).get("depth", 1)
        death_depths[f"ярус {d}"] = death_depths.get(f"ярус {d}", 0) + 1
        death_turns.append(r.turn_count)
        if r.death_cause:
            death_causes.append(r.death_cause[:120])

    # доля свободного текста vs кнопок — понять, чего не хватает в suggested_actions
    total_turns = db.query(func.count(Turn.id)).scalar() or 0
    # приблизительно: кнопочные вводы совпадают с одним из последних suggested_actions — 
    # без тяжёлой аналитики берём последние свободные вводы как сырьё для чтения
    recent_inputs = [
        t[0]
        for t in db.query(Turn.player_input)
        .filter(Turn.player_input != "[начало забега]")
        .order_by(Turn.id.desc())
        .limit(40)
        .all()
    ]

    # возвраты: сколько игроков сыграло больше одного забега
    users_with_runs = (
        db.query(Run.user_id, func.count(Run.id)).group_by(Run.user_id).all()
    )
    repeat_players = sum(1 for _, c in users_with_runs if c > 1)

    return {
        "users": total_users,
        "repeat_players": repeat_players,
        "runs": {"total": total_runs, **runs_by_status},
        "run_length_turns": {"avg": avg_len, "median": med_len},
        "avg_death_turn": round(sum(death_turns) / len(death_turns), 1) if death_turns else 0,
        "death_by_depth": death_depths,
        "recent_death_causes": death_causes[:10],
        "total_turns": total_turns,
        "recent_player_inputs": recent_inputs,
    }
