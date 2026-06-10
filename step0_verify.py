"""
Step 0 — verify marketdata.app response shape for ticker F.

Run this BEFORE the full screener:
    python step0_verify.py

It prints the raw JSON for F call and put so you can confirm exact field
names and that mid[0] exists.  If any field name differs from what fetch.py
expects, update FIELD_MAP in fetch.py — that is the only place to change.

The API token is read from .env (MARKETDATA_TOKEN=...).
It is NEVER printed, logged, or shown in any output.
"""
import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ.get("MARKETDATA_TOKEN")
if not TOKEN:
    sys.exit(
        "ERROR: MARKETDATA_TOKEN not set.\n"
        "Create a file called .env in this directory with:\n"
        "    MARKETDATA_TOKEN=your_token_here\n"
        "Then re-run this script."
    )

BASE = "https://api.marketdata.app/v1"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
TICKER = "F"


def check_side(side: str):
    url = f"{BASE}/options/chain/{TICKER}/"
    params = {"side": side, "strikeLimit": 1}
    print(f"\n{'='*60}")
    print(f"  {side.upper()} — GET {url}?side={side}&strikeLimit=1")
    print(f"{'='*60}")

    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
    except requests.RequestException as exc:
        print(f"Request failed: {exc}")
        return

    print(f"HTTP status : {r.status_code}")
    print(f"Rate-limit headers present:")
    for h in r.headers:
        if any(k in h.lower() for k in ("rate", "credit", "limit", "remain")):
            print(f"  {h}: {r.headers[h]}")

    if not r.ok:
        print(f"Non-OK response. Body: {r.text[:300]}")
        return

    try:
        data = r.json()
    except Exception as exc:
        print(f"Could not parse JSON: {exc}\nRaw: {r.text[:500]}")
        return

    print("\nFull JSON response:")
    print(json.dumps(data, indent=2))

    print("\n--- Field summary (index [0] values) ---")
    if isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, list) and len(val) > 0:
                print(f"  {key}[0] = {val[0]!r}")
            else:
                print(f"  {key} = {val!r}")

    print("\n--- Checklist ---")
    for field in ("bid", "ask", "mid", "volume", "openInterest",
                  "strike", "expiration", "underlyingPrice", "last"):
        present = field in data and isinstance(data[field], list) and len(data[field]) > 0
        val = data[field][0] if present else "MISSING"
        status = "OK " if present else "!!!"
        print(f"  [{status}] {field}[0] = {val!r}")


check_side("call")
check_side("put")

print("\n" + "="*60)
print("NEXT STEPS:")
print("  1. Review the checklist above.")
print("  2. If any field name differs from what you expect, update")
print("     FIELD_MAP in fetch.py (the only place to change).")
print("  3. Confirm mid[0] exists — if not, the (bid+ask)/2 fallback")
print("     in fetch.py will be used automatically.")
print("  4. Run: python scan.py --tickers F --dry-run  (then without --dry-run)")
print("="*60)
