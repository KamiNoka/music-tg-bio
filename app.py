#!/usr/bin/env python3
# Точка входа. Команды:
#   python app.py            — веб-интерфейс (Flask)
#   python app.py web        — то же
#   python app.py worker     — фоновый воркер (опрос источников → выходы)
#   python app.py setup      — консольная настройка (для VPS)
#   python app.py login      — вход в Telegram в терминале
import sys

USAGE = """Music → Telegram bio / Discord

Использование:
  python app.py [web]    веб-интерфейс на http://127.0.0.1:8765
  python app.py worker   фоновый воркер (движок)
  python app.py setup    настройка в терминале
  python app.py login    войти в Telegram в терминале

Для деплоя обычно: процесс web + процесс worker (см. Procfile).
"""


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "web"

    if cmd == "web":
        import threading
        import webbrowser
        import webapp

        url = "http://127.0.0.1:8765"
        print(f"Открываю {url}")
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        webapp.run()

    elif cmd == "worker":
        import asyncio
        import worker
        asyncio.run(worker.run())

    elif cmd == "setup":
        from cli import setup
        setup()

    elif cmd == "login":
        import settings_store as st
        from telegram_auth import cli_login

        st.ensure_db()
        tg = st.get_settings()["telegram"]
        if not (tg["api_id"] and tg["api_hash"]):
            print("Сначала задай api_id/api_hash (python app.py setup)")
            return
        me = cli_login(tg["api_id"], tg["api_hash"])
        print(f"✓ Вошёл как {me.first_name}")

    else:
        print(USAGE)


if __name__ == "__main__":
    main()
