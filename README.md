# Options Liquidity Screener

Scans US option chains via [marketdata.app](https://marketdata.app) and surfaces
tickers whose first OTM call **and** put have a small mid premium, tight bid/ask
spread, and real open interest.  Run it after 4 PM ET to get same-day data.

---

## Security first

**Your API token lives only in `.env` — it is never committed, never logged, never
shown in reports.**

- `.env` is in `.gitignore`.  Git will always ignore this file.
- If you accidentally expose your token, rotate it immediately on marketdata.app.

---

## One-time setup

### 1 — Prerequisites

| What | Version |
|------|---------|
| Python | 3.11 or newer |
| Git | any recent version |
| GitHub account | free at github.com |
| marketdata.app account | data subscription required |

Install Python: https://www.python.org/downloads/
Install Git: https://git-scm.com/downloads

### 2 — Create and activate a virtual environment

Open Terminal, navigate to the project folder, then:

```bash
cd /path/to/options-screener
python3 -m venv .venv
source .venv/bin/activate          # Mac / Linux
# .venv\Scripts\activate           # Windows
pip install -r requirements.txt
```

### 3 — Create your `.env` file

```bash
cp .env.example .env
```

Open `.env` in any text editor and replace `your_token_here` with your real
token from marketdata.app.  Save the file.  Do **not** add quotes around the token.

```
MARKETDATA_TOKEN=abc123yourtokenhere
```

---

## Step 0 — verify API response shape (do this first, once)

```bash
python step0_verify.py
```

This makes **two** real API calls (F call + put) and prints the raw JSON so you
can confirm field names match what the screener expects.  If any field name
differs, update `FIELD_MAP` in `fetch.py` — that is the only place to change.

---

## Running the screener

```bash
# Full scan of tickers.txt (run after 4 PM ET on a trading day)
python scan.py

# Spot-check one or more tickers
python scan.py --tickers F,TQQQ,SOFI

# Re-scan only yesterday's green names (faster, uses fewer API credits)
python scan.py --rescan-passes

# Count requests without hitting the API
python scan.py --dry-run
```

### Output files

| File | What it contains |
|------|-----------------|
| `report_YYYY-MM-DD.html` | Colour-coded sortable table — open in any browser |
| `results_YYYY-MM-DD.csv` | All metrics for every ticker (importable to Excel / Numbers) |
| `scanner.db` | SQLite database of every scan — used by `trends.py` |

### Colour legend

| Colour | Meaning |
|--------|---------|
| **GREEN** | Both call and put pass premium + spread |
| **YELLOW** | One wing passes |
| **RED** | Data present but spread too wide |
| **GREY** | Error / no chain data |

---

## Trend queries

```bash
# Show 10-session history for F
python trends.py --ticker F --days 10

# List tickers green on >= 8 of last 10 sessions
python trends.py --stable --days 10

# Custom threshold
python trends.py --stable --days 20 --min-green 15
```

---

## Tuning thresholds

All filter values are in `config.py`.  Edit them to match your risk tolerance:

```python
MIN_PREMIUM = 7       # minimum cost per contract in dollars
MAX_PREMIUM = 75      # maximum cost per contract
MAX_SPREAD_ABS = 0.05 # maximum bid/ask spread in dollars
MAX_SPREAD_PCT = 0.07 # maximum spread as % of mid  (7%)
MIN_OI  = 1000        # minimum open interest
MIN_VOL = 500         # minimum volume (OR with OI)
```

---

## Rate limits

- **Default**: `REQUESTS_PER_MINUTE = 60` in `config.py` (1 request/second).
- The seed list (~100 tickers) costs 200 requests — about 3–4 minutes at the
  default rate.
- If your plan allows more requests per minute, raise `REQUESTS_PER_MINUTE`.
- marketdata.app free tier: ~100 req/min documented; paid tiers are higher.
- The screener aborts if estimated requests would exceed `REQUEST_BUDGET`
  (default 300) — raise this if you expand the ticker list.

---

## Expanding the ticker list

Edit `tickers.txt` directly (one ticker per line), or build a large universe:

```bash
python universe.py                  # downloads ~8,000 Nasdaq/NYSE symbols
cp tickers_large.txt tickers.txt    # use it
python scan.py --dry-run            # check request count before running
```

Note: the large list has ~8,000 symbols; you will need to raise `REQUEST_BUDGET`
in `config.py` and probably run in batches.

---

## GitHub setup (first time — step by step)

These commands create a **private** repo and push the code.  Run them once from
inside the `options-screener` folder.

### Option A — GitHub CLI (easiest)

If you don't have the GitHub CLI, install it from https://cli.github.com then
run `gh auth login`.

```bash
# Inside your options-screener folder:
git init
git add .gitignore                         # FIRST: lock down .env before anything else
git commit -m "initial: security .gitignore"

git add .
git commit -m "feat: options liquidity screener"

gh repo create options-screener --private --source=. --remote=origin --push
```

### Option B — Create repo on github.com manually

1. Go to https://github.com/new
2. Name: `options-screener`
3. Set to **Private**
4. Click **Create repository** (do NOT add README/gitignore — you have them)
5. Copy the repo URL shown on screen (looks like `https://github.com/YourName/options-screener.git`)

Then in your Terminal:

```bash
git init
git add .gitignore
git commit -m "initial: security .gitignore"

git add .
git commit -m "feat: options liquidity screener"

git remote add origin https://github.com/YourName/options-screener.git
git branch -M main
git push -u origin main
```

---

## GitHub Actions — automated daily scans (no computer needed)

The file `.github/workflows/scan.yml` is already included.  It runs the scan
automatically at 5:05 PM ET on weekdays and commits the results back to your repo.

**You need to add your API token as a GitHub Secret:**

1. Go to your repo on github.com
2. Click **Settings** (top navigation bar)
3. In the left sidebar: **Secrets and variables → Actions**
4. Click **New repository secret**
5. Name: `MARKETDATA_TOKEN`
6. Value: paste your token (no quotes)
7. Click **Add secret**

That's it.  The workflow reads the secret into the environment — your token is
**never** written to any file or visible in logs.

To test the workflow manually before waiting for the schedule:
- Go to your repo → **Actions** tab → **Daily Options Scan** → **Run workflow**

Results (CSV, HTML, updated scanner.db) will appear as a new commit in your repo
after each run.  You can open `report_YYYY-MM-DD.html` directly in your browser
by clicking it in the repo file list and choosing **Raw** or **Download**.

---

## Rotate your token

If you ever share your screen, push `.env` by mistake, or suspect exposure:

1. Log in to marketdata.app and generate a new token
2. Update `.env` locally with the new token
3. Update the `MARKETDATA_TOKEN` secret in GitHub (Settings → Secrets)
4. Revoke the old token on marketdata.app

---

## Module overview

```
fetch.py      marketdata.app API calls ONLY — swap this for another provider
analyze.py    metrics + pass/fail logic — no I/O
report.py     HTML + CSV output
db.py         SQLite persistence
config.py     all tuneable constants
scan.py       main entry point
trends.py     historical query CLI
universe.py   optional — builds large symbol list
step0_verify.py  one-time API shape check
```
