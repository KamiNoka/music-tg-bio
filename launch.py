#!/usr/bin/env python3
# Диспетчер процессов для Railway: один start command на оба сервиса,
# роль выбирается переменной окружения PROC_TYPE (web | worker).
import os

proc = os.environ.get("PROC_TYPE", "web")

if proc == "worker":
    import asyncio
    import worker
    asyncio.run(worker.run())
else:
    # web: запускаем gunicorn, слушая порт от Railway
    port = os.environ.get("PORT", "8080")
    os.execvp("gunicorn", ["gunicorn", "-w", "1", "-b", f"0.0.0.0:{port}", "webapp:app"])
