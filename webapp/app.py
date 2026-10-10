"""
webapp/app.py - The phone version of your Life Assistant (Flask).

Run locally to try it:   python -m webapp.app   then open http://127.0.0.1:5000
On PythonAnywhere it is started through wsgi.py.
"""

import hmac
import os
import sys
import time
from datetime import date, datetime, timedelta
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from flask import (Flask, abort, flash, jsonify, redirect, render_template, request,
                   send_file, session, url_for)

import config
from collectors import food, trains
from database import create_tables, get_connection
from review import weekly_report

app = Flask(__name__)
app.secret_key = config.SECRET_KEY or os.urandom(32)
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=not app.debug and os.environ.get("LA_DEV") != "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=90),
)
create_tables(verbose=False)

NOT_SET = ("", "CHANGE-ME", "choose-a-password")


# ---------------------------------------------------------------- helpers

def daily_calorie_goal():
    return config.DAILY_CALORIE_BUDGET - config.WEEKLY_DEFICIT_TARGET / 7


def monday_of(d):
    return d - timedelta(days=d.weekday())


def parse_day(text):
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return date.today()


def to_float(text, default=0.0):
    try:
        return float(str(text).replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def food_totals(day):
    conn = get_connection()
    kcal, protein, fat, carbs = conn.execute(
        "SELECT COALESCE(SUM(calories),0), COALESCE(SUM(protein),0), "
        "COALESCE(SUM(fat),0), COALESCE(SUM(carbs),0) FROM food_log WHERE date = ?",
        (day.isoformat(),)).fetchone()
    conn.close()
    return {"calories": kcal, "protein": protein, "fat": fat, "carbs": carbs}


def german_hours(start, end):
    conn = get_connection()
    minutes = conn.execute(
        "SELECT COALESCE(SUM(minutes),0) FROM german_sessions WHERE date BETWEEN ? AND ?",
        (start.isoformat(), end.isoformat())).fetchone()[0]
    conn.close()
    return minutes / 60


def pct(value, target):
    return max(0, min(100, round(value / target * 100))) if target else 0


@app.template_filter("num")
def num_filter(value, digits=0):
    return f"{value:,.{digits}f}"


@app.context_processor
def inject_globals():
    return {"cfg": config, "today": date.today()}


# ---------------------------------------------------------------- login

def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("ok"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    if config.WEB_PASSWORD in NOT_SET:
        return render_template("login.html", not_configured=True)
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("password", ""), config.WEB_PASSWORD):
            session.clear()
            session["ok"] = True
            session.permanent = True
            target = request.args.get("next", "")
            return redirect(target if target.startswith("/") and not target.startswith("//")
                            else url_for("today"))
        time.sleep(1)  # slows down password guessing
        flash("Wrong password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------- Today

@app.route("/")
@login_required
def today():
    d = date.today()
    totals = food_totals(d)
    goal = daily_calorie_goal()
    week_hours = german_hours(monday_of(d), d)
    days_left = 7 - d.weekday()
    needed = max(config.WEEKLY_GERMAN_HOURS_TARGET - week_hours, 0)
    return render_template(
        "today.html", active="today", totals=totals, goal=goal,
        cal_pct=pct(totals["calories"], goal),
        protein_pct=pct(totals["protein"], config.DAILY_PROTEIN_TARGET),
        week_hours=week_hours, german_pct=pct(week_hours, config.WEEKLY_GERMAN_HOURS_TARGET),
        per_day_needed=needed / days_left, today_hours=german_hours(d, d))


@app.route("/next-train")
@login_required
def next_train_fragment():
    """Loaded by the Today page after it appears, so a slow train API never blocks it."""
    try:
        deps = trains.get_departures(config.HOME_STATION_ID, minutes=60)
    except Exception:
        return '<p class="muted">Train data not available right now.</p>'
    now = datetime.now()
    deps = sorted((x for x in deps if not x["cancelled"] and x["actual"] >= now
                   and config.TRAIN_DIRECTION.lower() in x["direction"].lower()),
                  key=lambda x: x["actual"])
    return render_template("_next_train.html", deps=deps[:2], now=now)


# ---------------------------------------------------------------- Food

@app.route("/food")
@login_required
def food_page():
    d = parse_day(request.args.get("d"))
    conn = get_connection()
    entries = conn.execute(
        "SELECT id, time, food_name, grams, calories, protein, fat, carbs "
        "FROM food_log WHERE date = ? ORDER BY time, id", (d.isoformat(),)).fetchall()
    conn.close()
    results, query = [], request.args.get("q", "").strip()
    if query:
        try:
            results = food.search_by_name(query)
            if not results:
                flash("No results. Try the German name, or add it manually.", "info")
        except requests.RequestException:
            flash("Food search isn't reachable from the server yet. Use manual entry.", "error")
    totals = food_totals(d)
    return render_template(
        "food.html", active="food", day=d, entries=entries, totals=totals,
        goal=daily_calorie_goal(), cal_pct=pct(totals["calories"], daily_calorie_goal()),
        results=results, query=query, tab=request.args.get("tab", "search"),
        prev_day=d - timedelta(days=1), next_day=d + timedelta(days=1))


@app.route("/food/add", methods=["POST"])
@login_required
def food_add():
    f = request.form
    d = parse_day(f.get("d"))
    name = f.get("name", "").strip()[:120]
    if not name:
        flash("Please enter a name.", "error")
        return redirect(url_for("food_page", d=d.isoformat(), tab="manual"))
    grams = to_float(f.get("grams"), 0)
    if f.get("per100") == "1":
        if grams <= 0:
            flash("Please enter how many grams you ate.", "error")
            return redirect(url_for("food_page", d=d.isoformat()))
        factor = grams / 100
        values = [to_float(f.get(k)) * factor for k in ("kcal", "protein", "fat", "carbs")]
    else:
        values = [to_float(f.get(k)) for k in ("kcal", "protein", "fat", "carbs")]
        grams = grams or None
    food.save_entry(name, grams, *values, day=d.isoformat())
    flash(f"Added {name} ({values[0]:.0f} kcal).", "ok")
    return redirect(url_for("food_page", d=d.isoformat()))


@app.route("/food/barcode", methods=["POST"])
@login_required
def food_barcode():
    d = request.form.get("d", date.today().isoformat())
    code = request.form.get("code", "").replace(" ", "")
    if not code.isdigit():
        flash("A barcode is digits only.", "error")
        return redirect(url_for("food_page", d=d, tab="barcode"))
    try:
        found = food.lookup_barcode(code)
    except requests.RequestException:
        flash("Barcode lookup isn't reachable from the server yet. Use manual entry.", "error")
        return redirect(url_for("food_page", d=d, tab="manual"))
    if not found:
        flash("Product not found. Add it manually with the values from the label.", "info")
        return redirect(url_for("food_page", d=d, tab="manual"))
    label, values = found
    return render_template("food_pick.html", active="food", d=d, label=label, v=values)


@app.route("/food/delete/<int:entry_id>", methods=["POST"])
@login_required
def food_delete(entry_id):
    conn = get_connection()
    row = conn.execute("SELECT date FROM food_log WHERE id = ?", (entry_id,)).fetchone()
    conn.execute("DELETE FROM food_log WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()
    flash("Entry deleted.", "ok")
    return redirect(url_for("food_page", d=row[0] if row else None))


# ---------------------------------------------------------------- German

@app.route("/german")
@login_required
def german_page():
    d = date.today()
    monday = monday_of(d)
    days = []
    for i in range(7):
        day = monday + timedelta(days=i)
        hours = german_hours(day, day)
        days.append({"day": day, "hours": hours})
    peak = max([x["hours"] for x in days] + [config.WEEKLY_GERMAN_HOURS_TARGET / 7, 0.1])
    conn = get_connection()
    sessions = conn.execute(
        "SELECT id, date, clock_in, clock_out, minutes FROM german_sessions "
        "ORDER BY clock_in DESC LIMIT 12").fetchall()
    conn.close()
    week = sum(x["hours"] for x in days)
    return render_template(
        "german.html", active="german", days=days, peak=peak, week=week,
        week_pct=pct(week, config.WEEKLY_GERMAN_HOURS_TARGET),
        daily_target=config.WEEKLY_GERMAN_HOURS_TARGET / 7, sessions=sessions)


@app.route("/german/add", methods=["POST"])
@login_required
def german_add():
    """For sessions the Mac tracker missed (e.g. learning on the go)."""
    d = parse_day(request.form.get("d"))
    minutes = to_float(request.form.get("minutes"))
    if not 0 < minutes <= 600:
        flash("Please enter minutes between 1 and 600.", "error")
        return redirect(url_for("german_page"))
    start = datetime.combine(d, datetime.now().time()).replace(microsecond=0)
    conn = get_connection()
    conn.execute(
        "INSERT INTO german_sessions (date, clock_in, clock_out, minutes, synced) "
        "VALUES (?, ?, ?, ?, 1)",
        (d.isoformat(), f"{start:%Y-%m-%d %H:%M:%S}",
         f"{start + timedelta(minutes=minutes):%Y-%m-%d %H:%M:%S}", minutes))
    conn.commit()
    conn.close()
    flash(f"Added {minutes:.0f} min of German.", "ok")
    return redirect(url_for("german_page"))


@app.route("/german/delete/<int:session_id>", methods=["POST"])
@login_required
def german_delete(session_id):
    conn = get_connection()
    conn.execute("DELETE FROM german_sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    flash("Session deleted.", "ok")
    return redirect(url_for("german_page"))


# ---------------------------------------------------------------- Trains

@app.route("/trains")
@login_required
def trains_page():
    station_id = request.args.get("sid") or config.HOME_STATION_ID
    station_name = request.args.get("sname") or config.HOME_STATION_NAME
    direction = request.args.get("dir", "").strip()
    search = request.args.get("search", "").strip()
    rows, stations, error = [], [], None
    try:
        if search:
            stations = trains.find_stations(search)
        else:
            rows = trains.get_departures(station_id, minutes=60)
            if direction:
                rows = [r for r in rows if direction.lower() in r["direction"].lower()]
            rows.sort(key=lambda r: r["planned"] or datetime.max)
    except PermissionError:
        error = "Deutsche Bahn rejected the API keys. Check local_settings.py."
    except Exception:
        error = "Train data isn't reachable from the server right now."
    return render_template(
        "trains.html", active="trains", rows=rows, stations=stations, error=error,
        station_id=station_id, station_name=station_name, direction=direction,
        search=search, now=datetime.now())


# ---------------------------------------------------------------- Weekly review

LABELS = {"weekly_deficit": "Calorie deficit", "german_hours": "German study",
          "avg_protein": "Avg protein / day", "food_logging": "Days food logged"}
UNITS = {"weekly_deficit": "kcal", "german_hours": "h", "avg_protein": "g",
         "food_logging": "days"}


@app.route("/review")
@login_required
def review_page():
    which = request.args.get("week", "this")
    this_monday = monday_of(date.today())
    final = which == "last"
    monday = this_monday - timedelta(days=7) if final else this_monday
    last_day = monday + timedelta(days=6) if final else date.today()
    rows = weekly_report.week_data(monday)
    results = weekly_report.evaluate(rows, last_day)
    weekly_report.make_chart(monday, rows, results, last_day, final, phone=True)
    if final:
        weekly_report.save_breaches(monday, results)
    conn = get_connection()
    breaches = conn.execute(
        "SELECT id, week_start, target_name, target, actual, note FROM breaches "
        "ORDER BY week_start DESC, target_name").fetchall()
    conn.close()
    return render_template(
        "review.html", active="review", which=which, monday=monday, final=final,
        results=results, breaches=breaches, labels=LABELS, units=UNITS,
        chart_version=int(time.time()))


@app.route("/review/chart/<week>.png")
@login_required
def review_chart(week):
    monday = parse_day(week)
    path = os.path.join(weekly_report.REPORTS_DIR, f"week_{monday.isoformat()}_phone.png")
    if not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="image/png", max_age=0)


@app.route("/review/note/<int:breach_id>", methods=["POST"])
@login_required
def review_note(breach_id):
    conn = get_connection()
    conn.execute("UPDATE breaches SET note = ? WHERE id = ?",
                 (request.form.get("note", "").strip()[:500] or None, breach_id))
    conn.commit()
    conn.close()
    flash("Note saved.", "ok")
    return redirect(url_for("review_page", week=request.form.get("week", "last")) + "#breaches")


# ---------------------------------------------------------------- API for the Mac

def api_auth():
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not config.API_TOKEN or not hmac.compare_digest(token, config.API_TOKEN):
        abort(403)


@app.route("/api/german-sessions", methods=["POST"])
def api_german_sessions():
    api_auth()
    items = request.get_json(silent=True)
    if not isinstance(items, list):
        abort(400)
    conn = get_connection()
    saved = 0
    for it in items:
        try:
            values = (str(it["date"])[:10], str(it["clock_in"])[:19],
                      str(it["clock_out"])[:19], float(it["minutes"]))
        except (KeyError, TypeError, ValueError):
            continue
        existing = conn.execute("SELECT id FROM german_sessions WHERE clock_in = ?",
                                (values[1],)).fetchone()
        if existing:
            conn.execute("UPDATE german_sessions SET clock_out = ?, minutes = ? WHERE id = ?",
                         (values[2], values[3], existing[0]))
        else:
            conn.execute("INSERT INTO german_sessions (date, clock_in, clock_out, minutes, "
                         "synced) VALUES (?, ?, ?, ?, 1)", values)
        saved += 1
    conn.commit()
    conn.close()
    return jsonify({"saved": saved})


@app.route("/api/today")
def api_today():
    api_auth()
    totals = food_totals(date.today())
    return jsonify({"calories": totals["calories"], "protein": totals["protein"]})


# ---------------------------------------------------------------- PWA bits

@app.route("/manifest.webmanifest")
def manifest():
    return jsonify({
        "name": "Life Assistant", "short_name": "Assistant",
        "start_url": "/", "display": "standalone",
        "background_color": "#f6f5f1", "theme_color": "#f6f5f1",
        "icons": [{"src": url_for("static", filename="icon-512.png"),
                   "sizes": "512x512", "type": "image/png"}],
    })


if __name__ == "__main__":
    os.environ.setdefault("LA_DEV", "1")
    app.config["SESSION_COOKIE_SECURE"] = False
    app.run(host="0.0.0.0", port=5000, debug=True)
