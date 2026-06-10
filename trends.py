"""
trends.py — query scan history from scanner.db.

Usage:
  python trends.py --ticker F --days 10
      Print spread / premium / OI history for F (both sides).

  python trends.py --stable --days 10
      List tickers that were GREEN on >=8 of the last 10 sessions.

  python trends.py --stable --days 10 --min-green 5
      Same but with a custom threshold.
"""
import argparse
import sqlite3
from pathlib import Path

DB_PATH = Path("scanner.db")


def _conn():
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"{DB_PATH} not found — run scan.py at least once first."
        )
    return sqlite3.connect(DB_PATH)


def _table(headers: list, rows: list):
    if not rows:
        print("  (no rows)")
        return
    widths = [
        max(len(str(h)), max((len(str(r[i])) for r in rows), default=0))
        for i, h in enumerate(headers)
    ]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt.format(*row))


def ticker_history(ticker: str, days: int = 10):
    with _conn() as conn:
        raw = conn.execute("""
            SELECT scan_date, side, strike, expiration,
                   spread_pct, premium_per_contract, open_interest,
                   overall_pass, color, error
            FROM scans
            WHERE ticker = ?
            ORDER BY scan_date DESC, side ASC
            LIMIT ?
        """, (ticker.upper(), days * 2)).fetchall()

    if not raw:
        print(f"No history for {ticker!r} in scanner.db")
        return

    print(f"\n=== {ticker.upper()} — last {days} sessions ===")
    headers = ["Date", "Side", "Strike", "Exp", "Spread%", "Prem$", "OI", "Pass", "Color", "Error"]
    rows = []
    for r in raw:
        rows.append([
            r[0], r[1],
            f"{r[2]:.2f}" if r[2] else "—",
            r[3] or "—",
            f"{r[4]:.1%}" if r[4] is not None else "—",
            f"${r[5]:.2f}" if r[5] is not None else "—",
            f"{int(r[6])}" if r[6] is not None else "—",
            "PASS" if r[7] else "fail",
            r[8] or "—",
            (r[9] or "")[:40],
        ])
    _table(headers, rows)


def stable_tickers(days: int = 10, min_green: int = 8):
    with _conn() as conn:
        raw = conn.execute("""
            SELECT
                ticker,
                COUNT(DISTINCT scan_date)         AS green_days,
                ROUND(AVG(spread_pct) * 100, 2)   AS avg_spread_pct,
                ROUND(AVG(open_interest))          AS avg_oi
            FROM scans
            WHERE overall_pass = 1
              AND scan_date >= date('now', :offset || ' days')
            GROUP BY ticker
            HAVING green_days >= :min_green
            ORDER BY green_days DESC, avg_spread_pct ASC
        """, {"offset": f"-{days}", "min_green": min_green}).fetchall()

    print(f"\n=== Stable tickers: green >= {min_green} of last {days} sessions ===")
    if not raw:
        print(f"  None found.")
        return
    headers = ["Ticker", "Green Days", "Avg Spread%", "Avg OI"]
    rows = [
        [r[0], r[1], f"{r[2]}%" if r[2] is not None else "—",
         f"{int(r[3])}" if r[3] is not None else "—"]
        for r in raw
    ]
    _table(headers, rows)


def main():
    parser = argparse.ArgumentParser(description="Query options scan history")
    parser.add_argument("--ticker",    help="Ticker symbol (e.g. F)")
    parser.add_argument("--stable",    action="store_true", help="List consistently-green tickers")
    parser.add_argument("--days",      type=int, default=10,  help="Look-back window (default 10)")
    parser.add_argument("--min-green", type=int, default=8,   help="Min green sessions for --stable")
    args = parser.parse_args()

    if args.ticker:
        ticker_history(args.ticker, args.days)
    elif args.stable:
        stable_tickers(args.days, args.min_green)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
