
import os
import plistlib
import subprocess
import sys
import time
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (BASE_DIR, DAILY_CALORIE_BUDGET, WEEKLY_DEFICIT_TARGET,
                    DAILY_PROTEIN_TARGET, WEEKLY_GERMAN_HOURS_TARGET,
                    HOME_STATION_ID, HOME_STATION_NAME)
from database import get_connection, create_tables
import remote

try:
    from config import SKIP_CALENDARS
except ImportError:
    SKIP_CALENDARS = ["Birthdays", "Geburtstage"]   
try:
    from config import TRAIN_DIRECTION
except ImportError:
    TRAIN_DIRECTION = "München"                     

AGENT_LABEL = "com.lifeassistant.briefing"
AGENT_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{AGENT_LABEL}.plist")


class CalendarError(Exception):
    pass


# For the definition of APple calendar 

def _event_store():
    try:
        import EventKit
        from Foundation import NSDate, NSRunLoop
    except ImportError:
        raise CalendarError("Missing library. Run: pip install pyobjc-framework-EventKit")

    status = EventKit.EKEventStore.authorizationStatusForEntityType_(EventKit.EKEntityTypeEvent)
    if status == 3:              # full access already granted
        return EventKit.EKEventStore.alloc().init()
    if status != 0:              # denied, restricted or write-only
        raise CalendarError("No access to Calendar. Allow it in System Settings → "
                            "Privacy & Security → Calendars (turn on PyCharm / Python, "
                            "Full Access).")
#The permission pop up shows in a mac only once
    store = EventKit.EKEventStore.alloc().init()
    result = {}

    def done(granted, error):
        result["granted"] = bool(granted)

    if hasattr(store, "requestFullAccessToEventsWithCompletion_"):   # macOS 14+
        store.requestFullAccessToEventsWithCompletion_(done)
    else:
        store.requestAccessToEntityType_completion_(EventKit.EKEntityTypeEvent, done)

    deadline = time.time() + 60
    while "granted" not in result and time.time() < deadline:
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.2))
    if not result.get("granted"):
        raise CalendarError("Calendar access was not granted. Allow it in System Settings → "
                            "Privacy & Security → Calendars.")
    return EventKit.EKEventStore.alloc().init()


def get_events(day):
    """All events on one day, sorted, as simple dicts."""
    from Foundation import NSDate
    store = _event_store()
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(days=1)
    predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
        NSDate.dateWithTimeIntervalSince1970_(start.timestamp()),
        NSDate.dateWithTimeIntervalSince1970_(end.timestamp()),
        None)

    events = []
    for e in store.eventsMatchingPredicate_(predicate) or []:
        calendar = e.calendar().title() if e.calendar() else ""
        if calendar in SKIP_CALENDARS:
            continue
        events.append({
            "title": e.title() or "(no title)",
            "start": datetime.fromtimestamp(e.startDate().timeIntervalSince1970()),
            "end": datetime.fromtimestamp(e.endDate().timeIntervalSince1970()),
            "all_day": bool(e.isAllDay()),
            "location": e.location() or "",
            "calendar": calendar,
        })
    events.sort(key=lambda ev: (not ev["all_day"], ev["start"]))
    return events


# food data fetching and extraction

def food_today():
    from_server = remote.get_today_food()
    if from_server is not None:
        return from_server
    today = date.today().isoformat()
    conn = get_connection()
    kcal, protein = conn.execute(
        "SELECT COALESCE(SUM(calories), 0), COALESCE(SUM(protein), 0) "
        "FROM food_log WHERE date = ?", (today,)).fetchone()
    conn.close()
    return kcal, protein


def german_this_week():
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    conn = get_connection()
    minutes = conn.execute(
        "SELECT COALESCE(SUM(minutes), 0) FROM german_sessions WHERE date BETWEEN ? AND ?",
        (monday.isoformat(), today.isoformat())).fetchone()[0]
    conn.close()
    return minutes / 60


def next_train():
    """Next departure towards TRAIN_DIRECTION, or None."""
    try:
        from collectors import trains
        deps = trains.get_departures(HOME_STATION_ID, minutes=60)
    except Exception:
        return None
    deps = [d for d in deps if not d["cancelled"]
            and TRAIN_DIRECTION.lower() in d["direction"].lower()
            and d["actual"] >= datetime.now()]
    return min(deps, key=lambda d: d["actual"]) if deps else None


# briefing about the day for a better outlook of me

def _event_line(ev):
    if ev["all_day"]:
        when = "all day     "
    else:
        when = f"{ev['start']:%H:%M}–{ev['end']:%H:%M} "
    place = f"  ({ev['location'][:35]})" if ev["location"] else ""
    return f"{when} {ev['title']}{place}"


def build_briefing(day=None):
    """Returns (full text for the screen, short text for a notification)."""
    day = day or date.today()
    is_today = day == date.today()
    lines = [f"\n  === {day:%A, %d %B} ==="]
    short = []

    # Calendar
    try:
        events = get_events(day)
        lines.append("  📅 Appointments")
        if not events:
            lines.append("     Nothing in your calendar. A free day!")
            short.append("No appointments")
        now = datetime.now()
        for ev in events:
            done = is_today and not ev["all_day"] and ev["end"] < now
            lines.append(f"     {_event_line(ev)}" + ("   ✓" if done else ""))
        timed = [ev for ev in events if not ev["all_day"]]
        if timed:
            first = timed[0]
            short.append(f"{len(events)} appointment(s), first {first['start']:%H:%M} "
                         f"{first['title']}")
        elif events:
            short.append(f"{len(events)} all-day event(s)")
        if is_today:
            tomorrow = [ev for ev in get_events(day + timedelta(days=1)) if not ev["all_day"]]
            if tomorrow:
                lines.append(f"     Tomorrow starts: {tomorrow[0]['start']:%H:%M} "
                             f"{tomorrow[0]['title']}")
    except CalendarError as e:
        lines.append(f"  📅 {e}")

    if is_today:
        # German
        hours = german_this_week()
        days_left = 7 - day.weekday()
        needed = max(WEEKLY_GERMAN_HOURS_TARGET - hours, 0)
        german = f"{hours:.1f} / {WEEKLY_GERMAN_HOURS_TARGET} h this week"
        if needed:
            german += f", about {needed / days_left:.1f} h/day to reach your target"
        else:
            german += ", target reached! 🎉"
        lines.append(f"  🇩🇪 German: {german}")
        short.append(f"German {hours:.1f}/{WEEKLY_GERMAN_HOURS_TARGET} h")

        # Food
        kcal, protein = food_today()
        goal = DAILY_CALORIE_BUDGET - WEEKLY_DEFICIT_TARGET / 7
        lines.append(f"  🍽  Food: {kcal:,.0f} / {goal:,.0f} kcal ({goal - kcal:,.0f} left), "
                     f"protein {protein:.0f} / {DAILY_PROTEIN_TARGET} g")

        # Train
        train = next_train()
        if train:
            delay = f" (+{train['delay']} min)" if train["delay"] > 0 else ""
            platform = f", Gl. {train['platform']}" if train["platform"] else ""
            mins = int((train["actual"] - datetime.now()).total_seconds() // 60)
            lines.append(f"  🚆 Next to {TRAIN_DIRECTION} from {HOME_STATION_NAME}: "
                         f"{train['line']} at {train['actual']:%H:%M}{delay}{platform} "
                         f"(in {mins} min)")
        else:
            lines.append(f"  🚆 No train towards {TRAIN_DIRECTION} found in the next hour.")

    return "\n".join(lines) + "\n", " · ".join(short)


#notifications and information in the shape of text

def notify(title, message):
    """Show a macOS notification."""
    def esc(s):
        return s.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(["osascript", "-e",
                    f'display notification "{esc(message)}" with title "{esc(title)}"'],
                   capture_output=True)


def send_morning_notification():
    create_tables()
    full, short = build_briefing()
    notify("Guten Morgen! ☀️", short or "Open your assistant for today's briefing.")
    # Also keep today's briefing as a text file you can open later
    os.makedirs(os.path.join(BASE_DIR, "reports"), exist_ok=True)
    with open(os.path.join(BASE_DIR, "reports", "today_briefing.txt"), "w") as f:
        f.write(full)


def turn_on_morning_notification():
    text = input("  What time? (e.g. 07:30): ").strip()
    try:
        t = datetime.strptime(text, "%H:%M")
    except ValueError:
        print("  Please use the format HH:MM, e.g. 07:30")
        return
    agent = {
        "Label": AGENT_LABEL,
        "ProgramArguments": [sys.executable, "-m", "collectors.daily_schedule", "--notify"],
        "WorkingDirectory": BASE_DIR,
        "StartCalendarInterval": {"Hour": t.hour, "Minute": t.minute},
        "StandardErrorPath": os.path.join(BASE_DIR, "reports", "briefing_errors.log"),
    }
    os.makedirs(os.path.dirname(AGENT_PATH), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "reports"), exist_ok=True)
    subprocess.run(["launchctl", "unload", AGENT_PATH], capture_output=True)
    with open(AGENT_PATH, "wb") as f:
        plistlib.dump(agent, f)
    subprocess.run(["launchctl", "load", AGENT_PATH], capture_output=True)
    print(f"  Done! You'll get a briefing notification every day at {t:%H:%M}.")
    print("  (If your Mac is asleep then, it arrives when it wakes up.)")
    send_morning_notification()
    print("  A test notification was sent just now.")


def turn_off_morning_notification():
    if os.path.exists(AGENT_PATH):
        subprocess.run(["launchctl", "unload", AGENT_PATH], capture_output=True)
        os.remove(AGENT_PATH)
        print("  Morning notification turned off.")
    else:
        print("  It wasn't turned on.")


#set of options to choose from

def run():
    while True:
        print("  --- Daily briefing ---")
        print("  1. Today")
        print("  2. Tomorrow's appointments")
        print("  3. Turn on morning notification")
        print("  4. Turn off morning notification")
        print("  0. Back")
        choice = input("  > ").strip()
        if choice == "1":
            print(build_briefing()[0])
        elif choice == "2":
            print(build_briefing(date.today() + timedelta(days=1))[0])
        elif choice == "3":
            turn_on_morning_notification()
        elif choice == "4":
            turn_off_morning_notification()
        elif choice == "0":
            break
        else:
            print("  Please choose 0-4.")


if __name__ == "__main__":
    if "--notify" in sys.argv:
        send_morning_notification()
    else:
        run()
