"""
scan.py — main entry point.

Usage:
  python scan.py                        scan all tickers in tickers.txt
  python scan.py --tickers F,TQQQ       spot-check specific tickers
  python scan.py --rescan-passes        only yesterday's green tickers
  python scan.py --dry-run              count requests; hit NO endpoints
"""
import argparse
import datetime
import logging
import os
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

# Load .env FIRST — before any module that reads os.environ
load_dotenv()

from analyze import analyze_side, classify_ticker, rank_tickers
from config import MAX_WORKERS, REQUEST_BUDGET
from db import init_db, save_rows
from fetch import fetch_ticker
from report import write_csv, write_html

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── ticker loading ────────────────────────────────────────────────────────────

def _load_tickers(path: str = "tickers.txt") -> list[str]:
    p = Path(path)
    if not p.exists():
        logger.error("tickers.txt not found at %s", path)
        sys.exit(1)
    raw = p.read_text(encoding="utf-8").replace(",", "\n")
    return [
        t.strip().upper()
        for t in raw.splitlines()
        if t.strip() and not t.strip().startswith("#")
    ]


def _load_yesterday_passes() -> list[str]:
    db_path = Path("scanner.db")
    if not db_path.exists():
        logger.warning("scanner.db not found — falling back to full tickers.txt")
        return _load_tickers()
    yesterday = str(datetime.date.today() - datetime.timedelta(days=1))
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT ticker FROM scans WHERE scan_date=? AND overall_pass=1",
            (yesterday,),
        ).fetchall()
    if not rows:
        logger.info("No passes for %s — running full scan", yesterday)
        return _load_tickers()
    tickers = [r[0] for r in rows]
    logger.info("Rescanning %d yesterday's green tickers", len(tickers))
    return tickers


# ── per-ticker work ───────────────────────────────────────────────────────────

def _process(ticker: str) -> dict:
    raw = fetch_ticker(ticker)
    call_r = analyze_side(raw["call"])
    put_r  = analyze_side(raw["put"])
    return {
        "ticker": ticker,
        "call":   call_r,
        "put":    put_r,
        "color":  classify_ticker(call_r, put_r),
    }


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Options liquidity screener")
    parser.add_argument("--tickers",       help="Comma-separated tickers to scan")
    parser.add_argument("--rescan-passes", action="store_true",
                        help="Only scan yesterday's green names")
    parser.add_argument("--dry-run",       action="store_true",
                        help="Estimate request count; do NOT call any API endpoints")
    args = parser.parse_args()

    # ── token check ──
    token = os.environ.get("MARKETDATA_TOKEN")
    if not token and not args.dry_run:
        logger.error(
            "MARKETDATA_TOKEN not set.\n"
            "Create a file named .env in this directory:\n"
            "    MARKETDATA_TOKEN=your_token_here\n"
            "Then re-run."
        )
        sys.exit(1)
    if token:
        logger.info("MARKETDATA_TOKEN loaded from environment (value not logged)")

    # ── build ticker list ──
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    elif args.rescan_passes:
        tickers = _load_yesterday_passes()
    else:
        tickers = _load_tickers()

    total_requests = len(tickers) * 2
    logger.info(
        "%d tickers → ~%d requests  (REQUEST_BUDGET=%d)",
        len(tickers), total_requests, REQUEST_BUDGET,
    )

    if total_requests > REQUEST_BUDGET:
        logger.error(
            "Estimated %d requests exceeds REQUEST_BUDGET=%d.  "
            "Reduce tickers or raise REQUEST_BUDGET in config.py.",
            total_requests, REQUEST_BUDGET,
        )
        sys.exit(1)

    if args.dry_run:
        logger.info("Dry run — no API calls made.")
        return

    # ── init DB ──
    init_db()
    scan_date = str(datetime.date.today())
    results: list[dict] = []
    request_count = 0
    error_count   = 0

    # ── concurrent scan ──
    logger.info("Starting scan with MAX_WORKERS=%d ...", MAX_WORKERS)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_process, t): t for t in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                row = future.result()
                results.append(row)
                request_count += 2
                c_err = row["call"].get("error")
                p_err = row["put"].get("error")
                if c_err or p_err:
                    error_count += 1
                detail = row["color"]
                if c_err:
                    detail += f" [call: {c_err}]"
                if p_err:
                    detail += f" [put: {p_err}]"
                logger.info("%-8s  %s", ticker, detail)
            except Exception as exc:
                logger.warning("%-8s  EXCEPTION: %s", ticker, exc)
                error_count += 1
                results.append({
                    "ticker": ticker,
                    "call": {"ticker": ticker, "side": "call", "error": str(exc)},
                    "put":  {"ticker": ticker, "side": "put",  "error": str(exc)},
                    "color": "GREY",
                })

    # ── post-process ──
    ranked = rank_tickers(results)

    color_counts: dict[str, int] = {}
    for r in ranked:
        c = r.get("color", "GREY")
        color_counts[c] = color_counts.get(c, 0) + 1

    # Grab the last credit info seen
    credits_info = ""
    for r in results:
        for side in ("call", "put"):
            s = r.get(side) or {}
            cr = s.get("credits_remaining")
            cu = s.get("credits_used")
            if cr is not None:
                credits_info = f"Credits used: {cu}  remaining: {cr}"
                break
        if credits_info:
            break

    summary_parts = [f"{k}: {v}" for k, v in sorted(color_counts.items())]
    logger.info(
        "Scan complete — %d tickers, %d requests, %d errors  |  %s",
        len(results), request_count, error_count, "  ".join(summary_parts),
    )
    if credits_info:
        logger.info(credits_info)

    # ── write outputs ──
    csv_path  = f"results_{scan_date}.csv"
    html_path = f"report_{scan_date}.html"

    write_csv(ranked, csv_path)
    logger.info("CSV  → %s", csv_path)

    write_html(
        ranked, html_path,
        scan_date=scan_date,
        total_tickers=len(tickers),
        total_requests=request_count,
        credits_info=credits_info,
        color_counts=color_counts,
    )
    logger.info("HTML → %s", html_path)

    save_rows(ranked, scan_date)
    logger.info("DB   → scanner.db updated")

    # ── final summary ──
    for color in ("GREEN", "YELLOW"):
        names = [r["ticker"] for r in ranked if r.get("color") == color]
        if names:
            logger.info("%s (%d): %s", color, len(names), ", ".join(names))


if __name__ == "__main__":
    main()
