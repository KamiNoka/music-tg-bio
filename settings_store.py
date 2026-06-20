# Доступ к настройкам/истории/состоянию через БД. Заменяет config.json для веб/воркера.
import json
from datetime import datetime, timezone
from pathlib import Path

from config import DEFAULT_CONFIG
from db import get_session, init_db
from models import AllowedUser, CurrentState, PlayHistory, Settings

_CONFIG_JSON = Path(__file__).parent / "config.json"


def _merge_defaults(data: dict) -> dict:
    """Дополняет настройки недостающими полями из дефолтов."""
    out = json.loads(json.dumps(DEFAULT_CONFIG))  # копия дефолта
    out.update(data or {})
    for key, val in DEFAULT_CONFIG.items():
        out.setdefault(key, val)
    return out


def ensure_db():
    """Создаёт таблицы, singleton-строки и переносит config.json при первом запуске."""
    init_db()
    with get_session() as s:
        settings = s.get(Settings, 1)
        if settings is None:
            settings = Settings(id=1, data={}, telegram_session="", running=False)
            # миграция из config.json, если он есть
            if _CONFIG_JSON.exists():
                try:
                    settings.data = json.loads(_CONFIG_JSON.read_text(encoding="utf-8"))
                except Exception:
                    settings.data = {}
            s.add(settings)
        if s.get(CurrentState, 1) is None:
            s.add(CurrentState(id=1, track="", source=""))
        s.commit()


# ---------- Настройки (формат dict, совместимый с providers/engine) ----------

def get_settings() -> dict:
    with get_session() as s:
        row = s.get(Settings, 1)
        return _merge_defaults(row.data if row else {})


def save_settings(data: dict):
    with get_session() as s:
        row = s.get(Settings, 1) or Settings(id=1)
        row.data = data
        s.add(row)
        s.commit()


def get_running() -> bool:
    with get_session() as s:
        row = s.get(Settings, 1)
        return bool(row.running) if row else False


def set_running(value: bool):
    with get_session() as s:
        row = s.get(Settings, 1) or Settings(id=1)
        row.running = value
        s.add(row)
        s.commit()


def get_session_string() -> str:
    with get_session() as s:
        row = s.get(Settings, 1)
        return (row.telegram_session or "") if row else ""


def set_session_string(value: str):
    with get_session() as s:
        row = s.get(Settings, 1) or Settings(id=1)
        row.telegram_session = value
        s.add(row)
        s.commit()


# ---------- Текущее состояние ----------

def set_current(track: str | None, source: str | None):
    now = datetime.now(timezone.utc)
    with get_session() as s:
        row = s.get(CurrentState, 1) or CurrentState(id=1)
        row.track = track or ""
        row.source = source or ""
        row.updated_at = now
        row.heartbeat = now
        s.add(row)
        s.commit()


def heartbeat():
    """Обновляет только отметку «воркер жив», не трогая трек."""
    with get_session() as s:
        row = s.get(CurrentState, 1) or CurrentState(id=1)
        row.heartbeat = datetime.now(timezone.utc)
        s.add(row)
        s.commit()


def get_current() -> dict:
    with get_session() as s:
        row = s.get(CurrentState, 1)
        if not row:
            return {"track": "", "source": "", "updated_at": None, "heartbeat": None}
        return {
            "track": row.track, "source": row.source,
            "updated_at": row.updated_at, "heartbeat": row.heartbeat,
        }


# ---------- История ----------

def add_history(track: str, source: str):
    """Пишет новый трек в историю. track = 'Исполнитель — Трек'."""
    artist, title = "", track
    if " — " in track:
        artist, title = track.split(" — ", 1)
    with get_session() as s:
        s.add(PlayHistory(artist=artist, title=title, track=track, source=source))
        s.commit()


# ---------- Доступ (Telegram-вход) ----------

def is_allowed(telegram_id: int) -> bool:
    with get_session() as s:
        return s.get(AllowedUser, telegram_id) is not None


def allowed_count() -> int:
    with get_session() as s:
        return s.query(AllowedUser).count()


def add_allowed(telegram_id: int, name: str = ""):
    with get_session() as s:
        if s.get(AllowedUser, telegram_id) is None:
            s.add(AllowedUser(telegram_id=telegram_id, name=name))
            s.commit()
