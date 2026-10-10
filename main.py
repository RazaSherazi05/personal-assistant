"""
main.py - The start button for your Life Assistant.
Run this file. More features get added to the menu as we build them.

The German tracker runs in the background by itself once you turn it on
(menu 2 -> "Run automatically").
"""

from database import create_tables
from collectors import food, german_tracker, trains, daily_schedule
from review import weekly_report
import remote


def main():
    create_tables()  # safe to run every time
    while True:
        print("\n=== Life Assistant ===")
        if remote.is_configured():
            print(f"(Food log and weekly review live in the web app: {remote.SERVER_URL})")
        print("1. Food log")
        print("2. German study hours")
        print("3. Weekly review")
        print("4. Train departures")
        print("5. Daily briefing")
        print("0. Quit")
        choice = input("> ").strip()
        if choice == "1":
            food.run()
        elif choice == "2":
            german_tracker.menu()
        elif choice == "3":
            weekly_report.run()
        elif choice == "4":
            trains.run()
        elif choice == "5":
            daily_schedule.run()
        elif choice == "0":
            print("Tschüss!")
            break
        else:
            print("Please choose a number from the menu.")


if __name__ == "__main__":
    main()
