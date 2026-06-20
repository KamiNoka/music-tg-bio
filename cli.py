# Консольный визард настройки и headless-запуск — для VPS без графики.
import time

from config import get_source, load_config, save_config
from engine import Engine
from providers.spotify import make_oauth
from providers.yandex import device_auth
from telegram_auth import cli_login


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{prompt}{suffix}: ").strip()
    return val or default


def _ask_yes(prompt: str, default: bool = False) -> bool:
    d = "Y/n" if default else "y/N"
    val = input(f"{prompt} ({d}): ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes", "д", "да")


def setup():
    """Интерактивная настройка в терминале."""
    config = load_config()
    print("\n=== Настройка Music → Telegram bio ===\n")

    # --- Telegram ---
    print("--- Telegram (my.telegram.org → API development tools) ---")
    config["telegram"]["api_id"] = int(_ask("api_id", str(config["telegram"]["api_id"] or "")) or 0)
    config["telegram"]["api_hash"] = _ask("api_hash", config["telegram"]["api_hash"])
    save_config(config)

    if _ask_yes("Войти в Telegram сейчас?", True):
        try:
            me = cli_login(config["telegram"]["api_id"], config["telegram"]["api_hash"])
            print(f"✓ Вошёл как {me.first_name}\n")
        except Exception as e:
            print(f"Ошибка входа: {e}\n")

    # --- Spotify ---
    print("--- Spotify (облако, ловит отовсюду) ---")
    spo = get_source(config, "spotify")
    if _ask_yes("Настроить Spotify?", bool(spo.get("refresh_token"))):
        spo["client_id"] = _ask("client_id", spo.get("client_id", ""))
        spo["client_secret"] = _ask("client_secret", spo.get("client_secret", ""))
        print("В приложении Spotify Redirect URI: http://127.0.0.1:8765/spotify/callback")
        try:
            oauth = make_oauth(spo["client_id"], spo["client_secret"], open_browser=False)
            print("\n1. Открой на своём компе:\n" + oauth.get_authorize_url())
            resp = _ask("\n2. Вставь URL, куда тебя перенаправило (или код)")
            code = oauth.parse_response_code(resp)
            token_info = oauth.get_access_token(code, check_cache=False)
            spo["refresh_token"] = token_info["refresh_token"]
            spo["enabled"] = True
            print("✓ Spotify подключён\n")
        except Exception as e:
            print(f"Ошибка Spotify: {e}\n")
    save_config(config)

    # --- Яндекс ---
    print("--- Яндекс Музыка (облако, надёжно с телефона) ---")
    yan = get_source(config, "yandex")
    if _ask_yes("Настроить Яндекс?", bool(yan.get("token"))):
        def on_code(c):
            print(f"\n1. Открой {c.verification_url}\n2. Введи код: {c.user_code}\n   (жду подтверждения...)")
        try:
            yan["token"] = device_auth(on_code)
            yan["enabled"] = True
            print("✓ Яндекс подключён\n")
        except Exception as e:
            print(f"Ошибка Яндекса: {e}\n")
    save_config(config)

    # --- MPRIS ---
    print("--- MPRIS (локально, только на машине с графикой) ---")
    mp = get_source(config, "mpris")
    mp["enabled"] = _ask_yes("Включить MPRIS?", mp.get("enabled", True))
    if mp["enabled"]:
        mp["player_filter"] = _ask("Фильтр плеера (пусто = любой)", mp.get("player_filter", ""))
    save_config(config)

    # --- Discord ---
    print("--- Discord Rich Presence (локально, две строки) ---")
    config.setdefault("discord", {"enabled": False, "client_id": ""})
    config["discord"]["enabled"] = _ask_yes("Включить Discord?", config["discord"].get("enabled", False))
    if config["discord"]["enabled"]:
        config["discord"]["client_id"] = _ask(
            "Application ID (discord.com/developers)", config["discord"].get("client_id", "")
        )
    save_config(config)

    # --- Bio ---
    print("--- Bio (Telegram, одна строка) ---")
    config["bio_template"] = _ask("Шаблон ({track} = трек)", config["bio_template"])
    config["interval"] = int(_ask("Интервал, сек", str(config["interval"])) or 20)
    save_config(config)

    print("\n✓ Готово. Запуск: python app.py run\n")


def run_headless():
    """Запуск движка без графики (для systemd на VPS)."""
    config = load_config()
    e = Engine()
    e.start(config)
    print("[run] движок запущен. Ctrl+C для остановки.")

    last_key, last_err = None, None
    try:
        # ждём, пока поток жив; печатаем смену трека и ошибки
        while True:
            time.sleep(1)
            st = e.get_status()
            if st.get("error") and st["error"] != last_err:
                print(f"[ошибка] {st['error']}")
                last_err = st["error"]
            if not e.is_running():
                break  # движок завершился сам (ошибка инициализации уже напечатана выше)
            key = (st.get("track"), st.get("source"))
            if key != last_key and st.get("track"):
                print(f"[bio] {st['source']}: {st['track']}")
                last_key = key
    except KeyboardInterrupt:
        print("\n[run] остановка...")
        e.stop()
