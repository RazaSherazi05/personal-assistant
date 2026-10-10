"""
review/weekly_report.py - Weekly review: charts, targets and breaches.

  - This week so far : progress chart, nothing recorded yet
  - Last week        : final chart, missed targets saved as breaches,
                       and you can write a note on what got in the way
  - Look back        : all past breaches with your notes

Charts are saved as images in the reports/ folder and opened automatically.
"""

import os
import subprocess
import sys
from datetime import date, timedelta

import matplotlib
matplotlib.use("Agg")  # draw to an image file, no pop-up window needed
import matplotlib.pyplot as plt

from config import (BASE_DIR, DAILY_CALORIE_BUDGET, WEEKLY_DEFICIT_TARGET,
                    DAILY_PROTEIN_TARGET, WEEKLY_GERMAN_HOURS_TARGET)
from database import get_connection, create_tables

REPORTS_DIR = os.path.join(BASE_DIR, "reports")
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Colors
BAR = "#2a78d6"
TARGET = "#52514e"
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"
GOOD = "#006300"
BAD = "#d03b3b"


# ---------------------------------------------------------------- data

def week_data(monday):
    """Collect daily calories, protein and German hours for Mon-Sun."""
    days = [monday + timedelta(days=i) for i in range(7)]
    conn = get_connection()
    food = {d: (k, p) for d, k, p in conn.execute(
        "SELECT date, SUM(calories), SUM(protein) FROM food_log "
        "WHERE date BETWEEN ? AND ? GROUP BY date",
        (str(days[0]), str(days[-1])))}
    german = dict(conn.execute(
        "SELECT date, SUM(minutes) FROM german_sessions "
        "WHERE date BETWEEN ? AND ? GROUP BY date",
        (str(days[0]), str(days[-1]))))
    conn.close()

    rows = []
    for d in days:
        kcal, protein = food.get(str(d), (None, None))
        rows.append({
            "day": d,
            "logged": kcal is not None,
            "calories": kcal or 0,
            "protein": protein or 0,
            "german_h": (german.get(str(d)) or 0) / 60,
        })
    return rows


def evaluate(rows, last_day):
    """Compare the week against the targets in config.py."""
    counted = [r for r in rows if r["day"] <= last_day]
    logged = [r for r in counted if r["logged"]]
    deficit = sum(DAILY_CALORIE_BUDGET - r["calories"] for r in logged)
    avg_protein = sum(r["protein"] for r in logged) / len(logged) if logged else 0
    german = sum(r["german_h"] for r in counted)
    return [
        # name, label, target, actual, unit, met?
        ("weekly_deficit", "Calorie deficit", WEEKLY_DEFICIT_TARGET, deficit, "kcal",
         deficit >= WEEKLY_DEFICIT_TARGET),
        ("german_hours", "German study", WEEKLY_GERMAN_HOURS_TARGET, german, "h",
         german >= WEEKLY_GERMAN_HOURS_TARGET),
        ("avg_protein", "Avg protein / day", DAILY_PROTEIN_TARGET, avg_protein, "g",
         avg_protein >= DAILY_PROTEIN_TARGET),
        ("food_logging", "Days food logged", len(counted), len(logged), "days",
         len(logged) >= len(counted)),
    ]


# ---------------------------------------------------------------- chart

def _fmt(value, unit):
    if unit == "h":
        return f"{value:.1f} h"
    if unit == "days":
        return f"{value:.0f} days"
    return f"{value:,.0f} {unit}"


def _panel(ax, rows, key, target, title, unit, last_day, phone=False):
    values = [r[key] for r in rows]
    ax.bar(range(7), values, width=0.6, color=BAR, zorder=2)
    ax.axhline(target, color=TARGET, linestyle="--", linewidth=1.2, zorder=3)
    title = f"{title}   ‒ ‒ daily target {_fmt(target, unit)}"
    if key in ("calories", "protein"):
        for i, r in enumerate(rows):
            if not r["logged"] and r["day"] <= last_day:
                ax.text(i, target * 0.04, "not\nlogged", ha="center", va="bottom",
                        fontsize=7, color=MUTED)
    ax.set_title(title, loc="left", fontsize=12 if phone else 11, color=INK, pad=8)
    ax.set_xticks(range(7))
    if phone:
        labels = [f"{DAY_NAMES[i][:2]}\n{r['day']:%d}" for i, r in enumerate(rows)]
    else:
        labels = [f"{DAY_NAMES[i]}\n{r['day']:%d.%m}" for i, r in enumerate(rows)]
    ax.set_xticklabels(labels, fontsize=10 if phone else 8, color=MUTED)
    ax.tick_params(axis="y", labelsize=10 if phone else 8, colors=MUTED, length=0)
    ax.tick_params(axis="x", length=0)
    ax.set_ylim(0, max(max(values), target) * 1.2 or 1)
    ax.grid(axis="y", color=GRID, linewidth=0.6, zorder=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")


def make_chart(monday, rows, results, last_day, final, phone=False):
    """Save the week's chart as a PNG. phone=True: narrow, charts only (for the web app)."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    daily_goal = DAILY_CALORIE_BUDGET - WEEKLY_DEFICIT_TARGET / 7
    panels = [("calories", daily_goal, "Calories eaten per day", "kcal"),
              ("german_h", WEEKLY_GERMAN_HOURS_TARGET / 7, "German study hours per day", "h"),
              ("protein", DAILY_PROTEIN_TARGET, "Protein per day (g)", "g")]

    if phone:
        fig = plt.figure(figsize=(5.2, 8.4), facecolor="#fcfcfb")
        axes = fig.subplots(3, 1, gridspec_kw={"top": 0.95, "bottom": 0.06, "hspace": 0.75,
                                               "left": 0.13, "right": 0.97})
        for ax, (key, target, title, unit) in zip(axes, panels):
            _panel(ax, rows, key, target, title.replace(" per day", ""), unit, last_day,
                   phone=True)
            ax.set_facecolor("#fcfcfb")
        path = os.path.join(REPORTS_DIR, f"week_{monday}_phone.png")
        fig.savefig(path, dpi=200)
        plt.close(fig)
        return path

    fig = plt.figure(figsize=(11, 9), facecolor="#fcfcfb")
    sunday = monday + timedelta(days=6)
    status = "Final" if final else f"In progress (up to {last_day:%a %d.%m})"
    fig.text(0.04, 0.965, f"Week {monday:%d.%m} – {sunday:%d.%m.%Y}",
             fontsize=16, weight="bold", color=INK)
    fig.text(0.04, 0.94, status, fontsize=10, color=MUTED)

    # Scorecard row
    for i, (_, label, target, actual, unit, met) in enumerate(results):
        x = 0.04 + i * 0.24
        fig.text(x, 0.895, label, fontsize=9, color=MUTED)
        fig.text(x, 0.865, _fmt(actual, unit), fontsize=15, weight="bold", color=INK)
        verdict = ("✔ MET" if met else "✘ MISSED") if final else (
            "on track" if met else "not yet")
        fig.text(x, 0.84, f"of {_fmt(target, unit)}   {verdict}", fontsize=9,
                 color=(GOOD if met else BAD) if final else MUTED)

    axes = fig.subplots(3, 1, gridspec_kw={"top": 0.79, "bottom": 0.06, "hspace": 0.6,
                                           "left": 0.07, "right": 0.97})
    for ax, (key, target, title, unit) in zip(axes, panels):
        _panel(ax, rows, key, target, title, unit, last_day)
        ax.set_facecolor("#fcfcfb")

    path = os.path.join(REPORTS_DIR, f"week_{monday}.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def open_file(path):
    if sys.platform == "darwin":
        subprocess.run(["open", path])
    print(f"  Chart saved: {path}")


# ---------------------------------------------------------------- breaches

def save_breaches(monday, results):
    """Record missed targets. Re-running keeps notes you already wrote."""
    conn = get_connection()
    breached = []
    for name, label, target, actual, unit, met in results:
        row = conn.execute("SELECT id FROM breaches WHERE week_start = ? AND target_name = ?",
                           (str(monday), name)).fetchone()
        if met:
            if row:
                conn.execute("DELETE FROM breaches WHERE id = ?", (row[0],))
            continue
        if row:
            conn.execute("UPDATE breaches SET target = ?, actual = ? WHERE id = ?",
                         (target, round(actual, 1), row[0]))
            breached.append((row[0], label, target, actual, unit))
        else:
            cur = conn.execute(
                "INSERT INTO breaches (week_start, target_name, target, actual) "
                "VALUES (?, ?, ?, ?)", (str(monday), name, target, round(actual, 1)))
            breached.append((cur.lastrowid, label, target, actual, unit))
    conn.commit()
    conn.close()
    return breached


def ask_for_notes(breached):
    if not breached:
        print("  All targets met. Stark! 💪")
        return
    print(f"\n  {len(breached)} target(s) missed. "
          "A short note now helps you spot patterns later.")
    conn = get_connection()
    for bid, label, target, actual, unit in breached:
        existing = conn.execute("SELECT note FROM breaches WHERE id = ?", (bid,)).fetchone()[0]
        print(f"\n  ✘ {label}: {_fmt(actual, unit)} of {_fmt(target, unit)}")
        if existing:
            print(f"    Your note: {existing}")
            prompt = "    New note (Enter to keep): "
        else:
            prompt = "    What got in the way? (Enter to skip): "
        note = input(prompt).strip()
        if note:
            conn.execute("UPDATE breaches SET note = ? WHERE id = ?", (note, bid))
    conn.commit()
    conn.close()


def look_back():
    conn = get_connection()
    rows = conn.execute("SELECT week_start, target_name, target, actual, note "
                        "FROM breaches ORDER BY week_start DESC, target_name").fetchall()
    conn.close()
    if not rows:
        print("  No breaches recorded yet.")
        return
    units = {"weekly_deficit": "kcal", "german_hours": "h",
             "avg_protein": "g", "food_logging": "days"}
    labels = {"weekly_deficit": "Calorie deficit", "german_hours": "German study",
              "avg_protein": "Avg protein", "food_logging": "Days food logged"}
    current = None
    for week, name, target, actual, note in rows:
        if week != current:
            print(f"\n  Week of {week}")
            current = week
        unit = units.get(name, "")
        print(f"   ✘ {labels.get(name, name):<17} {_fmt(actual, unit)} of {_fmt(target, unit)}")
        print(f"     Note: {note or '(none)'}")
    print()


# ---------------------------------------------------------------- menu

def review_week(monday, final):
    last_day = monday + timedelta(days=6) if final else date.today()
    rows = week_data(monday)
    results = evaluate(rows, last_day)
    open_file(make_chart(monday, rows, results, last_day, final))
    if final:
        ask_for_notes(save_breaches(monday, results))


def run():
    create_tables()
    this_monday = date.today() - timedelta(days=date.today().weekday())
    while True:
        print("  --- Weekly review ---")
        print("  1. This week so far")
        print("  2. Last week (final + record breaches)")
        print("  3. Look back at past breaches")
        print("  0. Back")
        choice = input("  > ").strip()
        if choice == "1":
            review_week(this_monday, final=False)
        elif choice == "2":
            review_week(this_monday - timedelta(days=7), final=True)
        elif choice == "3":
            look_back()
        elif choice == "0":
            break
        else:
            print("  Please choose 0-3.")


if __name__ == "__main__":
    run()
