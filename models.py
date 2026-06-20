# Модели БД.
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Settings(Base):
    """Singleton (id=1): все настройки приложения + управляющий флаг для воркера."""
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    # весь конфиг как JSON (формат как старый config.json: telegram, sources, discord, bio_*)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    # Telethon StringSession — отдельно, может быть длинным
    telegram_session: Mapped[str] = mapped_column(Text, default="")
    # команда воркеру: крутить или стоять
    running: Mapped[bool] = mapped_column(Boolean, default=False)


class PlayHistory(Base):
    """Лог прослушиваний — по записи на каждый новый трек."""
    __tablename__ = "play_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artist: Mapped[str] = mapped_column(String(512), default="")
    title: Mapped[str] = mapped_column(String(512), default="")
    track: Mapped[str] = mapped_column(String(1024), default="")  # полная строка 'Исполнитель — Трек'
    source: Mapped[str] = mapped_column(String(64), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class CurrentState(Base):
    """Singleton (id=1): что играет сейчас + heartbeat воркера — для дашборда и публичной страницы."""
    __tablename__ = "current_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    track: Mapped[str] = mapped_column(String(1024), default="")
    source: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    heartbeat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AllowedUser(Base):
    """Кому разрешён вход через Telegram (обычно только владелец)."""
    __tablename__ = "allowed_users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), default="")
