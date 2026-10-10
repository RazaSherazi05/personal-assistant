"""
local_settings_example.py - Template for your personal settings.

Copy this file to local_settings.py and fill in your values.
local_settings.py is listed in .gitignore, so it never goes to GitHub.
"""

# ---- Your targets ----
DAILY_CALORIE_BUDGET = 2200
WEEKLY_DEFICIT_TARGET = 2000
DAILY_PROTEIN_TARGET = 120
WEEKLY_GERMAN_HOURS_TARGET = 5
GERMAN_SITE = "example.com"

# ---- Trains: get free keys at developers.deutschebahn.com (Timetables API) ----
HOME_STATION_ID = "8000261"
HOME_STATION_NAME = "München Hbf"
TRAIN_DIRECTION = "München"
DB_CLIENT_ID = "your-client-id"
DB_API_KEY = "your-api-key"

# ---- Web app ----
# Make random values with:  python -c "import secrets; print(secrets.token_hex(32))"
WEB_PASSWORD = "choose-a-password"
SECRET_KEY = "random-string"
API_TOKEN = "another-random-string"     # must be the same on the Mac and the server
SERVER_URL = ""                         # on the Mac: https://yourname.pythonanywhere.com
