"""
universe.py — build a larger optionable symbol universe from Nasdaq Trader.

Run standalone:
    python universe.py                        # writes tickers_large.txt
    python universe.py --output my_tickers.txt

Source: Nasdaq Trader public symbol files (no auth, no key):
  https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt
  https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt

Filters applied:
  - Removes test issues
  - Removes symbols containing special chars (warrants, rights, units: ~+%$^/)
  - Removes symbols longer than 5 chars (funds, most ETNs)

NOTE: There is no price data in these symbol files.
  - The MIN_STOCK_PRICE filter in config.py applies at scan time if
    underlyingPrice is returned by the marketdata.app chain endpoint.
  - Tickers with no option chain return a 404 and are skipped automatically.
"""
import argparse
import re
import sys
from pathlib import Path

import requests

_NASDAQ_URL  = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
_OTHER_URL   = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
_USER_AGENT  = {"User-Agent": "options-screener-universe/1.0"}


def _fetch_symbols(url: str, label: str) -> list[str]:
    print(f"Fetching {label} from {url} ...")
    try:
        resp = requests.get(url, headers=_USER_AGENT, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  Warning: could not fetch {label}: {exc}", file=sys.stderr)
        return []

    symbols: list[str] = []
    for line in resp.text.splitlines()[1:]:   # skip header row
        if line.startswith("File Creation Time"):
            break
        parts = line.split("|")
        if len(parts) < 2:
            continue
        symbol = parts[0].strip()
        if not symbol:
            continue
        # Drop warrants/rights/units/preferred (special characters or long names)
        if re.search(r"[~+%$^/\s]", symbol):
            continue
        if len(symbol) > 5:
            continue
        symbols.append(symbol)

    print(f"  {len(symbols)} valid symbols")
    return symbols


def build_universe() -> list[str]:
    nasdaq = _fetch_symbols(_NASDAQ_URL, "Nasdaq-listed")
    other  = _fetch_symbols(_OTHER_URL,  "Other-listed (NYSE/AMEX)")
    all_syms = sorted(set(nasdaq + other))
    print(f"Total unique symbols: {len(all_syms)}")
    return all_syms


def main():
    parser = argparse.ArgumentParser(
        description="Build a large optionable symbol list from Nasdaq Trader"
    )
    parser.add_argument(
        "--output", default="tickers_large.txt",
        help="Output file (default: tickers_large.txt)",
    )
    args = parser.parse_args()

    symbols = build_universe()

    out = Path(args.output)
    out.write_text("\n".join(symbols) + "\n", encoding="utf-8")
    print(f"Wrote {len(symbols)} symbols to {out}")
    print()
    print("To use this list instead of the seed tickers:")
    print(f"  cp {out} tickers.txt")
    print("  python scan.py --dry-run   # check estimated request count first")
    print()
    print("Warning: this list has ~8,000+ symbols.")
    print("At 2 req/ticker and REQUEST_BUDGET=300 you will need to raise the")
    print("budget in config.py or run in batches.")


if __name__ == "__main__":
    main()
