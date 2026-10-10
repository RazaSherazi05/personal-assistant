

import fcntl
import os
import plistlib
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta

# Lets this file also run on its own in the background
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import BASE_DIR, GERMAN_SITE, WEEKLY_GERMAN_HOURS_TARGET
from database import get_connection, create_tables
import remote

CHECK_EVERY_SECONDS = 15
IDLE_LIMIT_SECONDS = 5 * 60      # no mouse/keyboard for 5 min = you've stepped away
MIN_SESSION_SECONDS = 30         # ignore accidental 5-second visits
SYNC_EVERY_SECONDS = 5 * 60      # retry sending to the web app this often

AGENT_LABEL = "com.lifeassistant.germantracker"
AGENT_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{AGENT_LABEL}.plist")
LOCK_PATH = os.path.join(BASE_DIR, "data", "german_tracker.lock")
LOG_PATH = os.path.join(BASE_DIR, "reports", "german_tracker.log")

# Asks Safari for the current page, but only if Safari is running AND in front.
# ("is running" check prevents this from opening Safari by itself.)
APPLESCRIPT = '''
if application "Safari" is running then
    tell application "Safari"
        if frontmost and (count of windows) > 0 then
            return URL of current tab of front window
        end if
    end tell
end if
return ""
'''


# ---------------------------------------------------------------- Mac checks

def get_active_safari_url():
    """URL of the front Safari tab, or '' if Safari isn't the active app."""
    try:
        result = subprocess.run(["osascript", "-e", APPLESCRIPT],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0 and "not allowed" in result.stderr.lower():
        print("  ! macOS blocked access to Safari. Allow it in System Settings → "
              "Privacy & Security → Automation (enable Safari under PyCharm).")
    return result.stdout.strip()


def get_idle_seconds():
    """Seconds since your last mouse movement or key press."""
    try:
        out = subprocess.run(["ioreg", "-c", "IOHIDSystem"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return 0
    match = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
    return int(match.group(1)) / 1_000_000_000 if match else 0


def is_studying(url, idle_seconds):
    return GERMAN_SITE.lower() in url.lower() and idle_seconds < IDLE_LIMIT_SECONDS


# ---------------------------------------------------------------- database

def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def start_session(now):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO german_sessions (date, clock_in, clock_out, minutes) VALUES (?, ?, ?, 0)",
        (now.strftime("%Y-%m-%d"), _fmt(now), _fmt(now)))
    conn.commit()
    session_id = cur.lastrowid
    conn.close()
    return session_id


def update_session(session_id, clock_in, now):
    minutes = (now - clock_in).total_seconds() / 60
    conn = get_connection()
    conn.execute("UPDATE german_sessions SET clock_out = ?, minutes = ? WHERE id = ?",
                 (_fmt(now), round(minutes, 2), session_id))
    conn.commit()
    conn.close()
    return minutes


def end_session(session_id, clock_in, end_time):
    minutes = update_session(session_id, clock_in, end_time)
    if minutes * 60 < MIN_SESSION_SECONDS:
        conn = get_connection()
        conn.execute("DELETE FROM german_sessions WHERE id = ?", (session_id,))
        conn.commit()
        conn.close()
        return 0
    return minutes


# ---------------------------------------------------------------- summary

def minutes_between(start_date, end_date):
    conn = get_connection()
    row = conn.execute(
        "SELECT COALESCE(SUM(minutes), 0) FROM german_sessions WHERE date >= ? AND date <= ?",
        (start_date, end_date)).fetchone()
    conn.close()
    return row[0]


def show_summary():
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    today_min = minutes_between(str(today), str(today))
    week_min = minutes_between(str(monday), str(today))
    target_min = WEEKLY_GERMAN_HOURS_TARGET * 60
    days_left = 7 - today.weekday()  # including today
    remaining = max(target_min - week_min, 0)

    print(f"\n  === German study ===")
    print(f"  Today:      {today_min / 60:.1f} h")
    print(f"  This week:  {week_min / 60:.1f} / {WEEKLY_GERMAN_HOURS_TARGET} h "
          f"({week_min / target_min * 100:.0f}%)")
    if remaining > 0:
        print(f"  To hit your target: {remaining / 60:.1f} h left, "
              f"about {remaining / days_left / 60:.1f} h per day for {days_left} day(s)\n")
    else:
        print("  Weekly target reached! 🎉\n")


# ---------------------------------------------------------------- main loop

def run():
    create_tables()
    # Only one tracker at a time, so no hour is ever counted twice
    lock = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("The German tracker is already running (probably in the background). "
              "Nothing else to do!")
        return
    # Stopping from the background (launchd) still closes the session cleanly
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    print(f"German tracker running. Watching Safari for '{GERMAN_SITE}'.", flush=True)
    print("Leave this running; stop it with the red square. Viel Erfolg!\n")

    if remote.is_configured():
        print(f"Sending finished sessions to {remote.SERVER_URL}", flush=True)
    session_id, clock_in = None, None
    last_sync = 0
    try:
        while True:
            now = datetime.now()
            idle = get_idle_seconds()
            studying = is_studying(get_active_safari_url(), idle)

            if studying and session_id is None:
                session_id, clock_in = start_session(now), now
                print(f"  {now:%H:%M}  Clocked in", flush=True)
            elif studying:
                update_session(session_id, clock_in, now)
            elif session_id is not None:
                # If you went idle, clock out at the moment you stopped, not now
                end_time = now - timedelta(seconds=idle) if idle >= IDLE_LIMIT_SECONDS else now
                end_time = max(end_time, clock_in)
                minutes = end_session(session_id, clock_in, end_time)
                if minutes:
                    print(f"  {end_time:%H:%M}  Clocked out ({minutes:.0f} min)", flush=True)
                session_id, clock_in = None, None
                last_sync = 0  # send the finished session right away

            # Send finished sessions to the web app (retries if you're offline)
            if time.time() - last_sync > SYNC_EVERY_SECONDS:
                sent = remote.push_german_sessions(skip_id=session_id)
                if sent:
                    print(f"  {now:%H:%M}  Synced {sent} session(s) to the web app", flush=True)
                last_sync = time.time()

            time.sleep(CHECK_EVERY_SECONDS)
    except KeyboardInterrupt:
        pass
    finally:
        if session_id is not None:
            end_session(session_id, clock_in, datetime.now())
            remote.push_german_sessions()
        print("\nTracker stopped.")


# ---------------------------------------------------------------- background mode

def is_background_on():
    return os.path.exists(AGENT_PATH)


def turn_on_background():
    os.makedirs(os.path.dirname(AGENT_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    agent = {
        "Label": AGENT_LABEL,
        "ProgramArguments": [sys.executable, "-m", "collectors.german_tracker"],
        "WorkingDirectory": BASE_DIR,
        "RunAtLoad": True,      # start when you log in
        "KeepAlive": True,      # restart if it ever crashes
        "StandardOutPath": LOG_PATH,
        "StandardErrorPath": LOG_PATH,
    }
    subprocess.run(["launchctl", "unload", AGENT_PATH], capture_output=True)
    with open(AGENT_PATH, "wb") as f:
        plistlib.dump(agent, f)
    subprocess.run(["launchctl", "load", AGENT_PATH], capture_output=True)
    print("  Done! The tracker now runs in the background and starts by itself "
          "every time you log in.")
    print("  You don't need to run german_tracker.py in PyCharm anymore.")
    print("  If macOS asks whether Python may control Safari, click Allow.")


def turn_off_background():
    if not is_background_on():
        print("  Background tracking wasn't on.")
        return
    subprocess.run(["launchctl", "unload", AGENT_PATH], capture_output=True)
    os.remove(AGENT_PATH)
    print("  Background tracking turned off.")


def show_log():
    if not os.path.exists(LOG_PATH):
        print("  No activity yet.")
        return
    with open(LOG_PATH) as f:
        lines = f.readlines()[-15:]
    print("\n  --- Recent tracker activity ---")
    for line in lines:
        print("  " + line.rstrip())
    print()


def menu():
    while True:
        status = "ON ✓" if is_background_on() else "off"
        print("  --- German study ---")
        print("  1. Hours this week")
        print(f"  2. Run automatically in background (now: {status})")
        print("  3. Turn off background tracking")
        print("  4. Recent clock-ins / clock-outs")
        print("  0. Back")
        choice = input("  > ").strip()
        if choice == "1":
            show_summary()
        elif choice == "2":
            turn_on_background()
        elif choice == "3":
            turn_off_background()
        elif choice == "4":
            show_log()
        elif choice == "0":
            break
        else:
            print("  Please choose 0-4.")


if __name__ == "__main__":
    run()
