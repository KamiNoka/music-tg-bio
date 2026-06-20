# Веб-GUI на Flask: настройка источников, авторизация, запуск движка.
import threading

from flask import Flask, jsonify, redirect, render_template, request

from config import get_source, load_config, save_config
from engine import Engine
from providers.spotify import make_oauth
from providers.yandex import device_auth
from telegram_auth import TelegramAuth, is_authorized

app = Flask(__name__)
engine = Engine()

# Состояние авторизаций (для polling со страницы)
yandex_state = {"status": "idle", "url": "", "code": "", "error": ""}
tg_auth: TelegramAuth | None = None
tg_state = {"step": "idle", "user": "", "error": ""}

# Кеш проверки авторизации Telegram: сессию открываем максимум один раз (иначе database is locked).
_tg_session_cache = {"checked": False, "value": None}
_tg_check_lock = threading.Lock()


# ---------- Главная страница и сохранение ----------

@app.route("/")
def index():
    return render_template("index.html", config=load_config())


@app.route("/save", methods=["POST"])
def save():
    config = load_config()
    f = request.form

    config["telegram"]["api_id"] = int(f.get("api_id") or 0)
    config["telegram"]["api_hash"] = f.get("api_hash", "").strip()
    config.setdefault("discord", {})
    config["discord"]["enabled"] = f.get("discord_enabled") == "on"
    config["discord"]["client_id"] = f.get("discord_client_id", "").strip()
    config["bio_template"] = f.get("bio_template", "🎧 {track}")
    config["bio_idle"] = f.get("bio_idle", "")
    config["interval"] = int(f.get("interval") or 20)
    config["bio_max_len"] = int(f.get("bio_max_len") or 70)

    for src in config["sources"]:
        t = src["type"]
        src["enabled"] = f.get(f"{t}_enabled") == "on"
        if t == "spotify":
            src["client_id"] = f.get("spotify_client_id", "").strip()
            src["client_secret"] = f.get("spotify_client_secret", "").strip()
        elif t == "yandex":
            # токен обычно ставится кнопкой авторизации, но разрешаем и ручной ввод
            manual = f.get("yandex_token", "").strip()
            if manual:
                src["token"] = manual
        elif t == "mpris":
            src["player_filter"] = f.get("mpris_player_filter", "").strip()

    save_config(config)
    return redirect("/")


@app.route("/reorder")
def reorder():
    """Меняет приоритет источника: ?type=spotify&dir=up|down."""
    config = load_config()
    srcs = config["sources"]
    t = request.args.get("type")
    direction = request.args.get("dir")
    i = next((k for k, s in enumerate(srcs) if s["type"] == t), None)
    if i is not None:
        j = i - 1 if direction == "up" else i + 1
        if 0 <= j < len(srcs):
            srcs[i], srcs[j] = srcs[j], srcs[i]
            save_config(config)
    return redirect("/")


# ---------- Spotify OAuth ----------

@app.route("/spotify/login")
def spotify_login():
    config = load_config()
    src = get_source(config, "spotify")
    if not (src and src.get("client_id") and src.get("client_secret")):
        return "Сначала сохрани client_id и client_secret Spotify", 400
    oauth = make_oauth(src["client_id"], src["client_secret"])
    return redirect(oauth.get_authorize_url())


@app.route("/spotify/callback")
def spotify_callback():
    config = load_config()
    src = get_source(config, "spotify")
    code = request.args.get("code")
    if not code:
        return redirect("/")
    oauth = make_oauth(src["client_id"], src["client_secret"])
    token_info = oauth.get_access_token(code, check_cache=False)
    src["refresh_token"] = token_info["refresh_token"]
    src["enabled"] = True
    save_config(config)
    return redirect("/")


# ---------- Яндекс device flow ----------

@app.route("/yandex/login", methods=["POST"])
def yandex_login():
    if yandex_state["status"] == "waiting":
        return jsonify(yandex_state)
    yandex_state.update(status="starting", url="", code="", error="")

    def worker():
        def on_code(c):
            yandex_state.update(status="waiting", url=c.verification_url, code=c.user_code)
        try:
            token = device_auth(on_code)
            config = load_config()
            src = get_source(config, "yandex")
            src["token"] = token
            src["enabled"] = True
            save_config(config)
            yandex_state.update(status="done")
        except Exception as e:
            yandex_state.update(status="error", error=str(e))

    threading.Thread(target=worker, daemon=True).start()
    return jsonify(yandex_state)


# ---------- Telegram пошаговый логин ----------

@app.route("/tg/send_code", methods=["POST"])
def tg_send_code():
    global tg_auth
    config = load_config()
    tg = config["telegram"]
    if not (tg["api_id"] and tg["api_hash"]):
        return jsonify({"step": "error", "error": "Сначала сохрани api_id и api_hash"})
    phone = request.json.get("phone", "").strip()
    try:
        # закрываем предыдущую попытку входа, чтобы не держать сессию двумя клиентами
        if tg_auth is not None:
            tg_auth.close()
        tg_auth = TelegramAuth(tg["api_id"], tg["api_hash"])
        res = tg_auth.send_code(phone)
        if res == "already":
            _tg_session_cache.update(checked=True, value={"ok": True, "name": ""})
            tg_state.update(step="done", user="(уже авторизован)", error="")
        else:
            tg_state.update(step="code", error="")
        return jsonify(tg_state)
    except Exception as e:
        tg_state.update(step="error", error=str(e))
        return jsonify(tg_state)


@app.route("/tg/sign_in", methods=["POST"])
def tg_sign_in():
    if not tg_auth:
        return jsonify({"step": "error", "error": "Сначала запроси код"})
    code = request.json.get("code", "").strip()
    password = request.json.get("password", "").strip()
    try:
        res = tg_auth.sign_in(code, password)
        if res == "need_password":
            tg_state.update(step="password", error="")
        elif res.startswith("ok:"):
            _tg_session_cache.update(checked=True, value={"ok": True, "name": res[3:]})
            tg_state.update(step="done", user=res[3:], error="")
        return jsonify(tg_state)
    except Exception as e:
        tg_state.update(step="error", error=str(e))
        return jsonify(tg_state)


# ---------- Запуск/остановка/статус ----------

@app.route("/start", methods=["POST"])
def start():
    engine.start(load_config())
    return jsonify(engine.get_status())


@app.route("/stop", methods=["POST"])
def stop():
    engine.stop()
    return jsonify(engine.get_status())


@app.route("/status")
def status():
    st = engine.get_status()
    # Сессию открываем максимум один раз и только когда она точно свободна:
    # движок не запущен и не идёт пошаговый логин (иначе SQLite database is locked).
    login_in_progress = tg_state["step"] in ("code", "password")
    with _tg_check_lock:
        if (
            not _tg_session_cache["checked"]
            and not engine.is_running()
            and not login_in_progress
        ):
            config = load_config()
            tg = config["telegram"]
            if tg["api_id"] and tg["api_hash"]:
                ok, name = is_authorized(tg["api_id"], tg["api_hash"])
                _tg_session_cache.update(checked=True, value={"ok": ok, "name": name})
            # если ключей ещё нет — не помечаем checked, проверим позже
    return jsonify(
        {"engine": st, "yandex": yandex_state, "tg_auth": tg_state,
         "tg_session": _tg_session_cache["value"]}
    )


def run(host="127.0.0.1", port=8765):
    app.run(host=host, port=port, debug=False)
