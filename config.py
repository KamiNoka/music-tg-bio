# Загрузка и сохранение настроек в config.json.
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"

# Дефолтная конфигурация. Порядок sources = приоритет источников.
DEFAULT_CONFIG = {
    "telegram": {"api_id": 0, "api_hash": ""},
    # Discord Rich Presence (две строки) — отдельный выход, локально через клиент Discord
    "discord": {"enabled": False, "client_id": ""},
    "bio_template": "🎧 {track}",
    "bio_idle": "",
    "interval": 20,
    "bio_max_len": 70,
    "sources": [
        {"type": "spotify", "enabled": False, "client_id": "", "client_secret": "", "refresh_token": ""},
        {"type": "yandex", "enabled": False, "token": ""},
        {"type": "mpris", "enabled": True, "player_filter": ""},
    ],
}


def load_config() -> dict:
    """Читает config.json, добавляя недостающие поля из дефолтов."""
    if not CONFIG_PATH.exists():
        return json.loads(json.dumps(DEFAULT_CONFIG))  # копия дефолта

    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    # Мягко дополняем верхнеуровневые ключи дефолтами (на случай старого конфига)
    for key, val in DEFAULT_CONFIG.items():
        data.setdefault(key, val)
    return data


def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_source(config: dict, source_type: str) -> dict | None:
    """Возвращает блок настроек источника по типу (spotify/yandex/mpris)."""
    for src in config.get("sources", []):
        if src.get("type") == source_type:
            return src
    return None
