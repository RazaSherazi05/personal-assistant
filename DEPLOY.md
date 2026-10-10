# Putting the web app online (PythonAnywhere, free plan)

Replace `YOURNAME` with your PythonAnywhere username and `GITHUBUSER` with your GitHub username.

## 1. Create the account

Sign up at [pythonanywhere.com](https://www.pythonanywhere.com) with the free **Beginner** plan. Your app will live at `https://YOURNAME.pythonanywhere.com`.

## 2. Get the code

Open **Consoles → Bash** and run:

```bash
git clone https://github.com/GITHUBUSER/life-assistant.git
cd life-assistant
mkvirtualenv --python=python3.11 la-env
pip install -r requirements.txt
mkdir -p data
```

## 3. Upload your private files

In the **Files** tab:

- Open `/home/YOURNAME/life-assistant/` and upload your `local_settings.py`.
- Open `/home/YOURNAME/life-assistant/data/` and upload your `assistant.db` from the Mac (from your project's `data` folder). This brings over everything you've logged so far.

## 4. Create the web app

In the **Web** tab:

1. **Add a new web app** → **Manual configuration** (not "Flask") → **Python 3.11**.
2. **Virtualenv:** `/home/YOURNAME/.virtualenvs/la-env`
3. **Source code:** `/home/YOURNAME/life-assistant`
4. Click the **WSGI configuration file** link, delete everything in it, and paste:
   ```python
   import sys
   path = "/home/YOURNAME/life-assistant"
   if path not in sys.path:
       sys.path.insert(0, path)
   from wsgi import application
   ```
   Then save.
5. Turn on **Force HTTPS**.
6. Click the green **Reload** button and open `https://YOURNAME.pythonanywhere.com`.

## 5. Add it to your iPhone

Open the address in **Safari** → **Share** button → **Add to Home Screen**. It then opens like an app.

## 6. Connect the Mac tracker

On the Mac, set this in `local_settings.py`:

```python
SERVER_URL = "https://YOURNAME.pythonanywhere.com"
```

Then restart background tracking: `python main.py` → `2` → `3` (turn off) → `2` (turn on). Finished study sessions now appear in the web app within a few minutes.

## Free-plan notes

- **Every 3 months**, open the Web tab and click **"Run until 3 months from today"**, or the site switches off. PythonAnywhere emails you a reminder first.
- Free accounts can only reach allow-listed websites. Open Food Facts and Deutsche Bahn need to be added; see the request below. Until then, manual food entry works, and food search, barcode lookup and trains show a short notice instead.

### Allowlist request

Post this in the [PythonAnywhere forums](https://www.pythonanywhere.com/forums/), or send it through **Send feedback** on any page:

> Hi! Could you please add these public APIs to the free-account allowlist?
>
> - `world.openfoodfacts.org` – Open Food Facts, the open food product database (API docs: https://openfoodfacts.github.io/openfoodfacts-server/api/)
> - `apis.deutschebahn.com` – Deutsche Bahn's official API Marketplace, Timetables API (docs: https://developers.deutschebahn.com/db-api-marketplace/apis/product/timetables)
>
> I'm using them in a small personal Flask project. Thanks!

## Updating later

After you push changes to GitHub:

```bash
cd ~/life-assistant && git pull
```

Then click **Reload** in the Web tab.
