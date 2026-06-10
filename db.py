"""
db.py — SQLite persistence.  One row per ticker per side per scan_date.
"""
import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path("scanner.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date            TEXT    NOT NULL,
    ticker               TEXT    NOT NULL,
    side                 TEXT    NOT NULL,
    bid                  REAL,
    ask                  REAL,
    mid                  REAL,
    strike               REAL,
    expiration           TEXT,
    underlying_price     REAL,
    volume               REAL,
    open_interest        REAL,
    premium_per_contract REAL,
    spread_dollars       REAL,
    spread_pct           REAL,
    pass_premium         INTEGER,
    pass_spread          INTEGER,
    pass_liquidity       INTEGER,
    overall_pass         INTEGER,
    color                TEXT,
    error                TEXT
);
CREATE INDEX IF NOT EXISTS idx_ticker_date ON scans (ticker, scan_date);
CREATE INDEX IF NOT EXISTS idx_date        ON scans (scan_date);
"""

_INSERT = """
INSERT INTO scans (
    scan_date, ticker, side,
    bid, ask, mid, strike, expiration, underlying_price,
    volume, open_interest, premium_per_contract,
    spread_dollars, spread_pct,
    pass_premium, pass_spread, pass_liquidity, overall_pass,
    color, error
) VALUES (?,?,?, ?,?,?,?,?,?, ?,?,?, ?,?, ?,?,?,?, ?,?)
"""


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(_SCHEMA)


def save_rows(rows: list, scan_date: str = None):
    today = scan_date or str(date.today())
    records = []
    for row in rows:
        color = row.get("color", "GREY")
        for side in ("call", "put"):
            s = row.get(side)
            if not s:
                continue
            pl = s.get("pass_liquidity")
            records.append((
                today,
                row["ticker"],
                side,
                s.get("bid"),
                s.get("ask"),
                s.get("mid"),
                s.get("strike"),
                s.get("expiration"),
                s.get("underlyingPrice"),
                s.get("volume"),
                s.get("openInterest"),
                s.get("premium_per_contract"),
                s.get("spread_dollars"),
                s.get("spread_pct"),
                int(s.get("pass_premium",  False)),
                int(s.get("pass_spread",   False)),
                int(pl) if pl is not None else None,
                int(s.get("overall_pass",  False)),
                color,
                s.get("error"),
            ))
    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(_INSERT, records)
