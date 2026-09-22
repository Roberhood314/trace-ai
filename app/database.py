import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./trace_ai.db")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(
    DATABASE_URL, connect_args=connect_args, pool_pre_ping=True,
    pool_size=max(1, int(os.getenv("DB_POOL_SIZE", "5"))),
    max_overflow=max(0, int(os.getenv("DB_MAX_OVERFLOW", "10"))),
    pool_recycle=max(60, int(os.getenv("DB_POOL_RECYCLE_SECONDS", "1800"))),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
