# Веб-интерфейс: дашборд, авторизация через Telegram, настройки в БД,
# история/статистика, публичная страница. Движок крутится отдельным процессом (worker.py),
# web управляет им флагом running в БД.
import os
import threading
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, redirect, render_template, request

import auth
import settings_store as st
from auth import login_required
from providers.spotify import make_oauth
from providers.yandex import device_auth
from telegram_auth import TelegramAuth, is_authorized

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")

st.ensure_db()

# Состояние авторизаций (для polling со страницы)
yandex_state = {"status": "idle", "url": "", "code": "", "error": ""}
tg_auth: TelegramAuth | None = None
tg_state = {"step": "idle", "user": "", "error": ""}

WORKER_ALIVE_SEC = 30  # воркер считается живым, если heartbeat свежее


def _worker_alive(current: dict) -> bool:
    hb = current.get("heartbeat")
    if not hb:
        return False
    if hb.tzinfo is None:
        hb = hb.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - hb < timedelta(seconds=WORKER_ALIVE_SEC)


# ---------- Авторизация ----------

@app.route("/login")
def login():
    if auth.is_logged_in():
        return redirect("/")
    return render_template("login.html", bot_username=auth.BOT_USERNAME, dev=auth.DEV_LOGIN)


@app.route("/auth/telegram")
def auth_telegram():
    data = request.args.to_dict()
    if auth.try_login(data):
        return redirect("/")
    return "Доступ запрещён или подпись неверна", 403


@app.route("/dev-login")
def dev_login_route():
    if auth.dev_login():
        return redirect("/")
    return "DEV_LOGIN выключен", 403


@app.route("/logout")
def logout():
    auth.logout()
    return redirect("/login")


# ---------- Дашборд и страницы ----------

@app.route("/")
@login_required
def index():
    return render_template("dashboard.html", config=st.get_settings(), user=request_user())


@app.route("/history")
@login_required
def history_page():
    return render_template("history.html", user=request_user())


@app.route("/public")
def public_page():
    return render_template("public.html")


def request_user() -> str:
    from flask import session
    return session.get("user_name", "")


# ---------- Сохранение настроек ----------

@app.route("/save", methods=["POST"])
@login_required
def save():
    config = st.get_settings()
    f = request.form

    config["telegram"]["api_id"] = int(f.get("api_id") or 0)
    config["telegram"]["api_hash"] = f.get("api_hash", "").strip()
    config.setdefault("discord", {})
    config["discord"]["mode"] = f.get("discord_mode", "off")
    config["discord"]["client_id"] = f.get("discord_client_id", "").strip()
    config["discord"]["user_token"] = f.get("discord_user_token", "").strip()
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
            manual = f.get("yandex_token", "").strip()
            if manual:
                src["token"] = manual
        elif t == "mpris":
            src["player_filter"] = f.get("mpris_player_filter", "").strip()

    st.save_settings(config)
    return redirect("/")


@app.route("/reorder")
@login_required
def reorder():
    config = st.get_settings()
    srcs = config["sources"]
    t = request.args.get("type")
    direction = request.args.get("dir")
    i = next((k for k, s in enumerate(srcs) if s["type"] == t), None)
    if i is not None:
        j = i - 1 if direction == "up" else i + 1
        if 0 <= j < len(srcs):
            srcs[i], srcs[j] = srcs[j], srcs[i]
            st.save_settings(config)
    return redirect("/")


# ---------- Spotify OAuth ----------

@app.route("/spotify/login")
@login_required
def spotify_login():
    config = st.get_settings()
    src = next((s for s in config["sources"] if s["type"] == "spotify"), None)
    if not (src and src.get("client_id") and src.get("client_secret")):
        return "Сначала сохрани client_id и client_secret Spotify", 400
    return redirect(make_oauth(src["client_id"], src["client_secret"]).get_authorize_url())


@app.route("/spotify/callback")
@login_required
def spotify_callback():
    config = st.get_settings()
    src = next((s for s in config["sources"] if s["type"] == "spotify"), None)
    code = request.args.get("code")
    if code and src:
        oauth = make_oauth(src["client_id"], src["client_secret"])
        token_info = oauth.get_access_token(code, check_cache=False)
        src["refresh_token"] = token_info["refresh_token"]
        src["enabled"] = True
        st.save_settings(config)
    return redirect("/")


# ---------- Яндекс device flow ----------

@app.route("/yandex/login", methods=["POST"])
@login_required
def yandex_login():
    if yandex_state["status"] == "waiting":
        return jsonify(yandex_state)
    yandex_state.update(status="starting", url="", code="", error="")

    def worker_thread():
        def on_code(c):
            yandex_state.update(status="waiting", url=c.verification_url, code=c.user_code)
        try:
            token = device_auth(on_code)
            config = st.get_settings()
            src = next((s for s in config["sources"] if s["type"] == "yandex"), None)
            if src:
                src["token"] = token
                src["enabled"] = True
                st.save_settings(config)
            yandex_state.update(status="done")
        except Exception as e:
            yandex_state.update(status="error", error=str(e))

    threading.Thread(target=worker_thread, daemon=True).start()
    return jsonify(yandex_state)


# ---------- Telegram пошаговый логин (StringSession в БД) ----------

@app.route("/tg/send_code", methods=["POST"])
@login_required
def tg_send_code():
    global tg_auth
    config = st.get_settings()
    tg = config["telegram"]
    if not (tg["api_id"] and tg["api_hash"]):
        return jsonify({"step": "error", "error": "Сначала сохрани api_id и api_hash"})
    phone = request.json.get("phone", "").strip()
    try:
        if tg_auth is not None:
            tg_auth.close()
        tg_auth = TelegramAuth(tg["api_id"], tg["api_hash"])
        res = tg_auth.send_code(phone)
        tg_state.update(step="done" if res == "already" else "code",
                        user="(уже авторизован)" if res == "already" else "", error="")
        return jsonify(tg_state)
    except Exception as e:
        tg_state.update(step="error", error=str(e))
        return jsonify(tg_state)


@app.route("/tg/sign_in", methods=["POST"])
@login_required
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
            tg_state.update(step="done", user=res[3:], error="")
        return jsonify(tg_state)
    except Exception as e:
        tg_state.update(step="error", error=str(e))
        return jsonify(tg_state)


# ---------- Управление воркером ----------

@app.route("/start", methods=["POST"])
@login_required
def start():
    st.set_running(True)
    return jsonify({"running": True})


@app.route("/stop", methods=["POST"])
@login_required
def stop():
    st.set_running(False)
    return jsonify({"running": False})


# ---------- API ----------

@app.route("/status")
@login_required
def status():
    cur = st.get_current()
    tg_ok, tg_name = is_authorized(
        st.get_settings()["telegram"].get("api_id"),
        st.get_settings()["telegram"].get("api_hash"),
    ) if not st.get_running() else (None, "")
    return jsonify({
        "running": st.get_running(),
        "worker_alive": _worker_alive(cur),
        "track": cur["track"],
        "source": cur["source"],
        "tg_session": {"ok": tg_ok, "name": tg_name} if tg_ok is not None else None,
        "yandex": yandex_state,
        "tg_auth": tg_state,
    })


@app.route("/api/stats")
@login_required
def api_stats():
    return jsonify(_compute_stats())


@app.route("/api/public")
def api_public():
    cur = st.get_current()
    return jsonify({
        "track": cur["track"],
        "source": cur["source"],
        "playing": _worker_alive(cur) and bool(cur["track"]),
        "recent": _recent(10),
        "top_artists": _top("artist", 5),
    })


def _recent(limit: int):
    from db import get_session
    from models import PlayHistory
    with get_session() as s:
        rows = s.query(PlayHistory).order_by(PlayHistory.started_at.desc()).limit(limit).all()
        return [{"track": r.track, "source": r.source,
                 "at": r.started_at.isoformat() if r.started_at else None} for r in rows]


def _top(field: str, limit: int):
    from sqlalchemy import func
    from db import get_session
    from models import PlayHistory
    col = getattr(PlayHistory, field)
    with get_session() as s:
        rows = (s.query(col, func.count().label("c"))
                .filter(col != "")
                .group_by(col).order_by(func.count().desc()).limit(limit).all())
        return [{"name": name, "count": c} for name, c in rows]


def _compute_stats():
    from db import get_session
    from models import PlayHistory
    with get_session() as s:
        total = s.query(PlayHistory).count()
    return {
        "total": total,
        "top_artists": _top("artist", 10),
        "top_tracks": _top("track", 10),
        "recent": _recent(20),
    }


def run(host="127.0.0.1", port=8765):
    app.run(host=host, port=port, debug=False)
