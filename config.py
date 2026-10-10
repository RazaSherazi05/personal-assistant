"""
config.py - Default settings.

Don't put personal values or keys here (this file is public on GitHub).
Put them in local_settings.py instead; anything set there overrides the
defaults below. See local_settings_example.py.
"""

import os
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "assistant.db")

# ---- Time zone (servers usually run on UTC) ----
TIMEZONE = "Europe/Berlin"

# ---- Nutrition targets ----
DAILY_CALORIE_BUDGET = 2200        # kcal you burn / allow yourself per day
WEEKLY_DEFICIT_TARGET = 2000       # kcal deficit you want per week
DAILY_PROTEIN_TARGET = 120         # grams

# ---- German learning targets ----
WEEKLY_GERMAN_HOURS_TARGET = 5     # hours per week
GERMAN_SITE = "example.com"        # the website you learn on

# ---- Trains (Deutsche Bahn Timetables API) ----
HOME_STATION_ID = "8000261"        # EVA number, from bahnhof.de (default: München Hbf)
HOME_STATION_NAME = "München Hbf"
TRAIN_DIRECTION = "München"        # direction for the "next train" line
DB_CLIENT_ID = ""
DB_API_KEY = ""

# ---- Calendar ----
SKIP_CALENDARS = ["Birthdays", "Geburtstage"]

# ---- Web app (phone version) ----
WEB_PASSWORD = ""                  # password to log in on your phone
SECRET_KEY = ""                    # random string, keeps you logged in safely
API_TOKEN = ""                     # shared secret between Mac tracker and server
SERVER_URL = ""                    # e.g. https://yourname.pythonanywhere.com (set on the Mac)

# ---- Your personal values override everything above ----
try:
    from local_settings import *   # noqa: F401,F403
except ImportError:
    pass

if hasattr(time, "tzset"):
    os.environ["TZ"] = TIMEZONE
    time.tzset()
