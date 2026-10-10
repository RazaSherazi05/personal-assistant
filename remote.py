"""
remote.py - Talks to your web app server from the Mac.

  - push_german_sessions(): sends finished German sessions to the server
  - get_today_food():       calories/protein logged today (on any device)

Does nothing if SERVER_URL or API_TOKEN is empty in local_settings.py.
"""

import requests

from config import SERVER_URL, API_TOKEN
from database import get_connection

TIMEOUT = 15


def is_configured():
    return bool(SERVER_URL and API_TOKEN)


def _headers():
    return {"Authorization": f"Bearer {API_TOKEN}"}


def push_german_sessions(skip_id=None):
    """Send unsynced, finished sessions. Returns how many were sent."""
    if not is_configured():
        return 0
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, date, clock_in, clock_out, minutes FROM german_sessions "
        "WHERE COALESCE(synced, 0) = 0 AND clock_out IS NOT NULL AND id != ?",
        (skip_id or -1,)).fetchall()
    if not rows:
        conn.close()
        return 0
    payload = [{"date": r[1], "clock_in": r[2], "clock_out": r[3], "minutes": r[4]}
               for r in rows]
    try:
        resp = requests.post(f"{SERVER_URL.rstrip('/')}/api/german-sessions",
                             json=payload, headers=_headers(), timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException:
        conn.close()
        return 0          # offline or server down: try again next time
    conn.executemany("UPDATE german_sessions SET synced = 1 WHERE id = ?",
                     [(r[0],) for r in rows])
    conn.commit()
    conn.close()
    return len(rows)


def get_today_food():
    """(calories, protein) from the server, or None if unavailable."""
    if not is_configured():
        return None
    try:
        resp = requests.get(f"{SERVER_URL.rstrip('/')}/api/today",
                            headers=_headers(), timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data["calories"], data["protein"]
    except (requests.RequestException, KeyError, ValueError):
        return None
