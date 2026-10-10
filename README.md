# Life Assistant

A personal assistant that tracks the things I want to improve every day, checks every week whether I hit my targets, and keeps a record of what got in the way when I didn't.

![Today, food log and weekly review on a phone](docs/preview.png)

*Screenshots use demo data.*

## What it does

| Feature | How it works |
|---|---|
| **Food log** | Search foods by name, look up packaged products by barcode, or enter values manually. Calories, protein, fat and carbs are calculated from the grams eaten. Data comes from [Open Food Facts](https://world.openfoodfacts.org). |
| **German study tracker** | Clocks in automatically when my language-learning site is the active tab in Safari on my Mac, and clocks out when I switch away or go idle for 5 minutes. Runs in the background and syncs sessions to the web app. |
| **Weekly review** | Compares each week against my targets: calorie deficit, study hours, average protein and logging consistency. It draws day-by-day charts, records every missed target as a breach, and asks for a short note on what went wrong so I can look back for patterns. |
| **Train departures** | Live departures, delays, cancellations and platform changes from the official Deutsche Bahn Timetables API. |
| **Daily briefing** | A morning Mac notification with today's Apple Calendar appointments, study progress, calories left and the next train. |
| **Phone web app** | A password-protected Flask app that works from the iPhone home screen, with tabs for Today, Food, German, Trains and Review. |

## How it fits together

```
 Mac (background)                      Server (Flask + SQLite)              iPhone
 ─────────────────                     ───────────────────────              ──────
 German tracker  ── finished sessions ──▶  /api/german-sessions
 Morning briefing ◀── today's food ─────   /api/today
                                           Web pages  ◀──────────────────── Home-screen app
                                             │
                                             ├─ Open Food Facts API
                                             └─ Deutsche Bahn Timetables API
```

## Tech

Python · Flask · SQLite · matplotlib · requests · AppleScript (Safari) · EventKit via PyObjC (Apple Calendar) · launchd (background jobs) · PythonAnywhere (hosting)

## Project structure

```
collectors/   food.py, german_tracker.py, trains.py, daily_schedule.py
review/       weekly_report.py   (targets, breaches, charts)
webapp/       Flask app, templates and styles for the phone
remote.py     Mac ⇄ server sync
database.py   SQLite tables
config.py     defaults; personal values go in local_settings.py (not in git)
main.py       terminal menu on the Mac
```

## Run it yourself

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp local_settings_example.py local_settings.py   # add your targets and keys
python main.py                                   # terminal version
python -m webapp.app                             # web version on http://127.0.0.1:5000
```

The train feature needs free API keys from the [DB API Marketplace](https://developers.deutschebahn.com/db-api-marketplace) (Timetables API). The German tracker and the calendar briefing only run on macOS. Hosting steps are in [DEPLOY.md](DEPLOY.md).

## Status

In beta. I'm using it every day and improving it as I go. Ideas for later include saved meals, barcode scanning with the phone camera, and monthly trend views.
