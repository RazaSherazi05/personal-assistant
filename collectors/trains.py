
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import quote

import requests

from config import (HOME_STATION_ID, HOME_STATION_NAME,
                    DB_CLIENT_ID, DB_API_KEY)

API = "https://apis.deutschebahn.com/db-api-marketplace/apis/timetables/v1"
TIMEOUT = 20


def _get(path):
    resp = requests.get(f"{API}/{path}", timeout=TIMEOUT, headers={
        "DB-Client-Id": DB_CLIENT_ID,
        "DB-Api-Key": DB_API_KEY,
        "Accept": "application/xml",
    })
    if resp.status_code in (401, 403):
        raise PermissionError("DB rejected the keys")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return ET.fromstring(resp.content)


def _parse_time(value):
    """DB times look like 2610091513 = 26-10-09 15:13."""
    return datetime.strptime(value, "%y%m%d%H%M") if value else None


# ---------------------------------------------------------------- API calls

def get_departures(station_id, minutes=60):
    now = datetime.now()
    trains = {}

    # 1. Planned timetable for this hour and the next one(s)
    hour = now.replace(minute=0, second=0, microsecond=0)
    while hour <= now + timedelta(minutes=minutes):
        root = _get(f"plan/{station_id}/{hour:%y%m%d}/{hour:%H}")
        for s in (root.findall("s") if root is not None else []):
            dp, tl = s.find("dp"), s.find("tl")
            if dp is None or tl is None:
                continue  # this train ends here, no departure
            category, line = tl.get("c", ""), dp.get("l")
            path = (dp.get("ppth") or "").split("|")
            trains[s.get("id")] = {
                "planned": _parse_time(dp.get("pt")),
                "actual": None,
                "line": f"{category} {line}" if line else f"{category} {tl.get('n', '')}",
                "direction": path[-1] if path and path[-1] else "?",
                "planned_platform": dp.get("pp"),
                "platform": dp.get("pp"),
                "cancelled": False,
            }
        hour += timedelta(hours=1)

    # 2. Live changes
    root = _get(f"fchg/{station_id}")
    for s in (root.findall("s") if root is not None else []):
        train, dp = trains.get(s.get("id")), s.find("dp")
        if train is None or dp is None:
            continue
        if dp.get("ct"):
            train["actual"] = _parse_time(dp.get("ct"))
        if dp.get("cp"):
            train["platform"] = dp.get("cp")
        if dp.get("cs") == "c":
            train["cancelled"] = True
        if dp.get("cpth"):
            train["direction"] = dp.get("cpth").split("|")[-1] or train["direction"]

    # 3. Keep only what leaves in the chosen window
    result = []
    for t in trains.values():
        t["actual"] = t["actual"] or t["planned"]
        t["delay"] = int((t["actual"] - t["planned"]).total_seconds() // 60) if t["planned"] else 0
        t["platform_changed"] = bool(t["platform"] and t["planned_platform"]
                                     and t["platform"] != t["planned_platform"])
        if t["actual"] and now - timedelta(minutes=1) <= t["actual"] <= now + timedelta(minutes=minutes):
            result.append(t)
    return result


def find_stations(name):
    root = _get(f"station/{quote(name)}")
    if root is None:
        return []
    return [(s.get("eva"), s.get("name")) for s in root.findall("station")][:8]


# ---------------------------------------------------------------- display

def print_board(rows, station_name, direction_filter=""):
    if direction_filter:
        rows = [r for r in rows if direction_filter.lower() in r["direction"].lower()]
    rows.sort(key=lambda r: r["planned"] or datetime.max)

    now = datetime.now()
    print(f"\n  === Departures {station_name} ({now:%H:%M}) ===")
    if not rows:
        print("  No departures found" + (f" towards '{direction_filter}'." if direction_filter else "."))
        return

    for r in rows:
        planned = f"{r['planned']:%H:%M}" if r["planned"] else "--:--"
        if r["cancelled"]:
            status = "CANCELLED ✘"
        elif r["delay"] > 0:
            status = f"+{r['delay']} min → {r['actual']:%H:%M}"
        else:
            status = "on time"
        in_min = int((r["actual"] - now).total_seconds() // 60) if r["actual"] else None
        leaving = (f"in {in_min} min" if in_min is not None and in_min >= 0
                   and not r["cancelled"] else "")
        platform = f"Gl. {r['platform']}" if r["platform"] else ""
        if r["platform_changed"]:
            platform += " (changed!)"
        print(f"  {planned}  {r['line']:<7} {r['direction'][:28]:<28} "
              f"{platform:<18} {status:<20} {leaving}")
    print()


# ---------------------------------------------------------------- menu

def show_home(direction_filter=""):
    print_board(get_departures(HOME_STATION_ID), HOME_STATION_NAME, direction_filter)


def other_station():
    name = input("  Station name: ").strip()
    if not name:
        return
    stations = find_stations(name)
    if not stations:
        print("  No station found. Try the official name, e.g. 'München Marienplatz'.")
        return
    for i, (_, sname) in enumerate(stations, start=1):
        print(f"  {i}. {sname}")
    choice = input("  Pick a number: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(stations):
        sid, sname = stations[int(choice) - 1]
        print_board(get_departures(sid), sname)


def run():
    actions = {
        "1": lambda: show_home(),
        "2": lambda: show_home(input("  Direction contains (e.g. München, Freising): ").strip()),
        "3": other_station,
    }
    while True:
        print("  --- Trains ---")
        print(f"  1. Next departures from {HOME_STATION_NAME}")
        print(f"  2. {HOME_STATION_NAME}, filtered by direction")
        print("  3. Another station")
        print("  0. Back")
        choice = input("  > ").strip()
        if choice == "0":
            break
        action = actions.get(choice)
        if action is None:
            print("  Please choose 0-3.")
            continue
        try:
            action()
        except PermissionError:
            print("  DB rejected your keys. Check DB_CLIENT_ID and DB_API_KEY in config.py, "
                  "and that your app is subscribed to the Timetables API.")
        except (requests.RequestException, ET.ParseError) as e:
            print(f"  Couldn't get train data: {e}")


if __name__ == "__main__":
    run()
