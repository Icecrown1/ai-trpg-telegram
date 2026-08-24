from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean, DateTime, Date,
    ForeignKey, JSON,
)
from sqlalchemy.orm import relationship
from .db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(128))
    first_name = Column(String(128))
    created_at = Column(DateTime, default=datetime.utcnow)

    # daily free-tier turn counter
    turns_today = Column(Integer, default=0)
    turns_date = Column(Date, default=date.today)

    # meta-progression between runs
    total_runs = Column(Integer, default=0)
    deepest_level = Column(Integer, default=0)
    best_gold = Column(Integer, default=0)

    runs = relationship("Run", back_populates="user")


class Run(Base):
    __tablename__ = "runs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    status = Column(String(16), default="active")  # active | dead | won | abandoned
    death_cause = Column(Text)

    # character + world state — backend is the source of truth
    state = Column(JSON, nullable=False, default=dict)

    # rolling summary of older events (AI Dungeon model)
    summary = Column(Text, default="")
    turn_count = Column(Integer, default=0)

    user = relationship("User", back_populates="runs")
    turns = relationship("Turn", back_populates="run", order_by="Turn.id")


class Turn(Base):
    __tablename__ = "turns"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("runs.id"), index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    player_input = Column(Text, nullable=False)
    narration = Column(Text, nullable=False)
    rolls = Column(JSON, default=list)          # dice results shown to the player
    suggested_actions = Column(JSON, default=list)
    state_delta = Column(JSON, default=dict)
    summarized = Column(Boolean, default=False)  # already folded into run.summary

    run = relationship("Run", back_populates="turns")
