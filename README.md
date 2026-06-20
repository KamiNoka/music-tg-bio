# music-tg-bio

Персональный веб-сервис: показывает текущий трек в **bio Telegram** и/или в **Discord**,
ведёт **историю прослушиваний**, статистику и публичную страницу «что я слушаю».
Доступ к управлению — через вход по Telegram.

## Архитектура

Два процесса вокруг общей БД:
- **web** (Flask) — интерфейс, авторизация, настройки, история, публичная страница.
- **worker** — опрашивает источники и пишет в выходы; управляется флагом из веба.
- **БД** — Postgres (`DATABASE_URL`) в облаке, SQLite (`data.db`) локально.

### Источники → где работают
| | Облако | Дома |
|---|---|---|
| Spotify (облако) | ✅ | ✅ |
| Яндекс (Ynison) | ✅ | ✅ |
| MPRIS (локальный плеер) | ❌ | ✅ |

### Выходы
- **Telegram bio** — одна строка по шаблону (`🎧 {track}`, можно текст до/после).
- **Discord Custom Status** («мысль» у ника) — через user-токен (⚠ selfbot, риск бана), работает в облаке.
- **Discord Rich Presence** — «Слушает …» под ником, только дома (нужен локальный Discord).

## Локальный запуск

```bash
./venv/bin/pip install -r requirements.txt   # ynison-зависимости: см. ниже
DEV_LOGIN=1 OWNER_TELEGRAM_ID=<твой id> SECRET_KEY=dev ./venv/bin/python app.py web
./venv/bin/python app.py worker              # в отдельном терминале
```
Локально вход — кнопкой «Dev-вход» (виджет Telegram не работает на localhost).

Команды: `app.py web` | `app.py worker` | `app.py setup` (визард для VPS) | `app.py login`.

## Деплой на Railway

1. Создай проект, подключи плагин **PostgreSQL** (даст `DATABASE_URL`).
2. Переменные окружения:
   - `SECRET_KEY` — случайная строка (Flask session).
   - `BOT_TOKEN`, `BOT_USERNAME` — бот из BotFather; `/setdomain` = домен Railway (для Telegram-входа).
   - `OWNER_TELEGRAM_ID` — твой Telegram id (первый вход застолбит владельца).
3. `Procfile` поднимает два процесса: `web` (gunicorn) и `worker`.
4. Spotify Redirect URI и домен Telegram-бота: `https://<app>.up.railway.app/...`.
5. Telegram-сессию задать: войти в вебе (телефон→код→2FA) — StringSession сохранится в БД.

Перенос на свой VPS позже — те же два процесса (systemd) + локальный Postgres/SQLite.

## Яндекс через Ynison
Нужна git-версия `yandex-music[ynison]` (на PyPI пока нет ynison):
```bash
pip install --no-build-isolation "yandex-music[ynison] @ git+https://github.com/MarshalX/yandex-music-api.git"
```
В РФ домены/бэкенд Яндекса могут блокироваться — провайдер сам резолвит через DoH и форсит IPv4;
при DPI-блокировке нужен обход/VPN. (На Railway за границей блокировок нет.)

## Заметки
- bio меняется у **user-аккаунта** (не бота) — вход под своим номером, сессия в БД (StringSession).
- Интервал ≥ 10 сек — Telegram банит за частую смену профиля.
- Точка отката: git-тег `checkpoint-local-v1` (стабильная локальная версия до веб-рефактора).
