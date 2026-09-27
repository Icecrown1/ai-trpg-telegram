from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
# pre_ping проверяет соединение при выдаче из пула, recycle не даёт брать протухшие (Replit/Neon
# рвут простаивающие SSL-соединения). Во время раздумий мастера соединение в пул уже возвращено.
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True,
                       pool_recycle=240)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
