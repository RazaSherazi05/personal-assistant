

from datetime import datetime

import requests

from config import DAILY_CALORIE_BUDGET, WEEKLY_DEFICIT_TARGET, DAILY_PROTEIN_TARGET
from database import get_connection

HEADERS = {"User-Agent": "LifeAssistant/0.1 (personal project)"}
TIMEOUT = 20  # seconds
SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
BARCODE_URL = "https://world.openfoodfacts.org/api/v2/product/{}.json"


# ---------------------------------------------------------------- helpers

def _to_float(value):
    try:
        if isinstance(value, str):
            value = value.replace(",", ".")
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _per_100g(product):
    """Pull calories/protein/fat/carbs per 100 g out of an Open Food Facts product."""
    n = product.get("nutriments", {})
    kcal = n.get("energy-kcal_100g")
    if kcal is None and n.get("energy_100g") is not None:
        kcal = _to_float(n["energy_100g"]) / 4.184  # kJ -> kcal
    if kcal is None:
        return None
    return {
        "calories": _to_float(kcal),
        "protein": _to_float(n.get("proteins_100g")),
        "fat": _to_float(n.get("fat_100g")),
        "carbs": _to_float(n.get("carbohydrates_100g")),
    }


def _ask_float(prompt):
    while True:
        text = input(prompt).strip().replace(",", ".")
        try:
            return float(text)
        except ValueError:
            print("  Please type a number, e.g. 120")


def _product_label(product):
    name = product.get("product_name") or "Unnamed product"
    brand = product.get("brands")
    return f"{name} ({brand})" if brand else name


# ---------------------------------------------------------------- lookups

def search_by_name(query, max_results=8):
    params = {
        "search_terms": query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": 25,
        "fields": "product_name,brands,nutriments",
    }
    resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    results = []
    for product in resp.json().get("products", []):
        values = _per_100g(product)
        if values and product.get("product_name"):
            results.append((_product_label(product), values))
        if len(results) >= max_results:
            break
    return results


def lookup_barcode(barcode):
    url = BARCODE_URL.format(barcode)
    resp = requests.get(url, params={"fields": "product_name,brands,nutriments"},
                        headers=HEADERS, timeout=TIMEOUT)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != 1:
        return None
    product = data.get("product", {})
    values = _per_100g(product)
    if not values:
        return None
    return _product_label(product), values


# ---------------------------------------------------------------- database

def save_entry(food_name, grams, calories, protein, fat, carbs, day=None):
    """Save one food item. day = 'YYYY-MM-DD' to log for another day (default today)."""
    now = datetime.now()
    conn = get_connection()
    conn.execute(
        """INSERT INTO food_log (date, time, food_name, grams, calories, protein, fat, carbs)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (day or now.strftime("%Y-%m-%d"), now.strftime("%H:%M"), food_name, grams,
         round(calories, 1), round(protein, 1), round(fat, 1), round(carbs, 1)),
    )
    conn.commit()
    conn.close()
    print(f"  Saved: {food_name} - {calories:.0f} kcal, "
          f"{protein:.1f} g protein, {fat:.1f} g fat, {carbs:.1f} g carbs")


def save_from_per_100g(food_name, values):
    grams = _ask_float("  How many grams did you eat? ")
    factor = grams / 100
    save_entry(food_name, grams,
               values["calories"] * factor, values["protein"] * factor,
               values["fat"] * factor, values["carbs"] * factor)


def undo_last_entry():
    conn = get_connection()
    row = conn.execute("SELECT id, food_name, calories FROM food_log "
                       "ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        print("  Nothing to undo.")
    elif input(f"  Delete '{row[1]}' ({row[2]:.0f} kcal)? (y/n) ").strip().lower() == "y":
        conn.execute("DELETE FROM food_log WHERE id = ?", (row[0],))
        conn.commit()
        print("  Deleted.")
    conn.close()


def show_today():
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    rows = conn.execute(
        "SELECT time, food_name, grams, calories, protein, fat, carbs "
        "FROM food_log WHERE date = ? ORDER BY time", (today,)).fetchall()
    conn.close()

    daily_goal = DAILY_CALORIE_BUDGET - WEEKLY_DEFICIT_TARGET / 7
    totals = [sum(r[i] or 0 for r in rows) for i in range(3, 7)]

    print(f"\n  === Today ({today}) ===")
    if not rows:
        print("  Nothing logged yet.")
    for t, name, grams, kcal, *_ in rows:
        amount = f"{grams:.0f} g" if grams else "-"
        print(f"  {t}  {name[:40]:<40} {amount:>7}  {kcal:>6.0f} kcal")
    print("  " + "-" * 64)
    print(f"  Calories: {totals[0]:.0f} / {daily_goal:.0f} kcal "
          f"({daily_goal - totals[0]:.0f} left to stay on deficit target)")
    print(f"  Protein:  {totals[1]:.0f} / {DAILY_PROTEIN_TARGET} g")
    print(f"  Fat: {totals[2]:.0f} g    Carbs: {totals[3]:.0f} g\n")


# ---------------------------------------------------------------- menu actions

def add_by_name():
    query = input("  Food name: ").strip()
    if not query:
        return
    print("  Searching...")
    results = search_by_name(query)
    if not results:
        print("  No results. Try another word (German names often work better) "
              "or use manual entry.")
        return
    for i, (label, v) in enumerate(results, start=1):
        print(f"  {i}. {label[:50]:<50} {v['calories']:>5.0f} kcal/100 g")
    choice = input("  Pick a number (or Enter to cancel): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(results):
        label, values = results[int(choice) - 1]
        save_from_per_100g(label, values)


def add_by_barcode():
    code = input("  Barcode number: ").strip().replace(" ", "")
    if not code.isdigit():
        print("  A barcode is digits only.")
        return
    found = lookup_barcode(code)
    if not found:
        print("  Product not found. Use manual entry with the values from the label.")
        return
    label, values = found
    print(f"  Found: {label} - {values['calories']:.0f} kcal per 100 g")
    save_from_per_100g(label, values)


def add_manually():
    name = input("  What did you eat? ").strip()
    if not name:
        return
    calories = _ask_float("  Calories (kcal): ")
    protein = _ask_float("  Protein (g): ")
    fat = _ask_float("  Fat (g): ")
    carbs = _ask_float("  Carbs (g): ")
    save_entry(name, None, calories, protein, fat, carbs)


def run():
    actions = {
        "1": add_by_name,
        "2": add_by_barcode,
        "3": add_manually,
        "4": show_today,
        "5": undo_last_entry,
    }
    while True:
        print("  --- Food log ---")
        print("  1. Search food by name")
        print("  2. Enter barcode")
        print("  3. Manual entry")
        print("  4. Today's summary")
        print("  5. Undo last entry")
        print("  0. Back")
        choice = input("  > ").strip()
        if choice == "0":
            break
        action = actions.get(choice)
        if action is None:
            print("  Please choose 0-5.")
            continue
        try:
            action()
        except requests.RequestException:
            print("  Couldn't reach Open Food Facts (internet or server issue). "
                  "Try again in a minute, or use manual entry.")


if __name__ == "__main__":
    run()
