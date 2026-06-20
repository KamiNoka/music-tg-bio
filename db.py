# Подключение к БД: Postgres (DATABASE_URL, напр. на Railway) или SQLite локально.
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


def _db_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        # Railway/Heroku отдают 'postgres://', SQLAlchemy ждёт 'postgresql+psycopg://'
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url
    # локально — файл SQLite рядом с проектом
    return f"sqlite:///{Path(__file__).parent / 'data.db'}"


engine = create_engine(_db_url(), pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db():
    """Создаёт таблицы (если нет). Импорт models здесь, чтобы избежать циклов."""
    import models  # noqa: F401
    Base.metadata.create_all(engine)


def get_session():
    return SessionLocal()
