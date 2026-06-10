"""
analyze.py — compute metrics and pass/fail flags from fetched data.

Pure functions: no I/O, no side effects, no imports from fetch/report/db.
"""
from config import (
    MAX_PREMIUM, MAX_SPREAD_ABS, MAX_SPREAD_PCT,
    MIN_OI, MIN_PREMIUM, MIN_VOL,
)


def analyze_side(raw: dict) -> dict:
    """
    Enrich a raw fetch dict with computed metrics and pass/fail flags.
    Never raises — errors produce overall_pass=False with a reason string.
    """
    result = dict(raw)

    if raw.get("error"):
        result.update({
            "premium_per_contract": None,
            "spread_dollars": None,
            "spread_pct": None,
            "pass_premium": False,
            "pass_spread": False,
            "pass_liquidity": None,
            "overall_pass": False,
            "fail_reasons": [raw["error"]],
        })
        return result

    bid = raw.get("bid")
    ask = raw.get("ask")
    mid = raw.get("mid")

    # No quote: bid or ask is 0 / None
    if not bid or not ask:
        result.update({
            "premium_per_contract": None,
            "spread_dollars": None,
            "spread_pct": None,
            "pass_premium": False,
            "pass_spread": False,
            "pass_liquidity": None,
            "overall_pass": False,
            "fail_reasons": ["no quote (bid/ask zero or missing)"],
        })
        return result

    spread_dollars = ask - bid
    premium_per_contract = mid * 100 if mid is not None else None
    spread_pct = (spread_dollars / mid) if (mid and mid > 0) else None

    fail_reasons = []

    # --- Premium ---
    pass_premium = (
        premium_per_contract is not None
        and MIN_PREMIUM <= premium_per_contract <= MAX_PREMIUM
    )
    if not pass_premium:
        if premium_per_contract is None:
            fail_reasons.append("mid unavailable")
        elif premium_per_contract < MIN_PREMIUM:
            fail_reasons.append(f"premium too low (${premium_per_contract:.2f})")
        else:
            fail_reasons.append(f"premium too high (${premium_per_contract:.2f})")

    # --- Spread ---
    pass_spread = bool(
        spread_dollars <= MAX_SPREAD_ABS
        and spread_pct is not None
        and spread_pct <= MAX_SPREAD_PCT
    )
    if not pass_spread:
        if spread_dollars > MAX_SPREAD_ABS:
            fail_reasons.append(f"spread ${spread_dollars:.3f} > ${MAX_SPREAD_ABS}")
        if spread_pct and spread_pct > MAX_SPREAD_PCT:
            fail_reasons.append(f"spread_pct {spread_pct:.1%} > {MAX_SPREAD_PCT:.0%}")

    # --- Liquidity (optional — absent fields are not a fail) ---
    oi  = raw.get("openInterest")
    vol = raw.get("volume")
    if oi is not None or vol is not None:
        pass_liquidity = bool(
            (oi  is not None and oi  >= MIN_OI)
            or (vol is not None and vol >= MIN_VOL)
        )
        if not pass_liquidity:
            fail_reasons.append(f"low liquidity (OI={oi}, Vol={vol})")
    else:
        pass_liquidity = None  # unknown — not counted as a fail

    overall_pass = pass_premium and pass_spread

    result.update({
        "premium_per_contract": premium_per_contract,
        "spread_dollars": spread_dollars,
        "spread_pct": spread_pct,
        "pass_premium": pass_premium,
        "pass_spread": pass_spread,
        "pass_liquidity": pass_liquidity,
        "overall_pass": overall_pass,
        "fail_reasons": fail_reasons,
    })
    return result


def classify_ticker(call_result: dict, put_result: dict) -> str:
    """
    GREEN  — both wings pass premium + spread
    YELLOW — one wing passes, or premium outside budget on both
    RED    — spread fail on at least one wing (data present, spread too wide)
    GREY   — error / no data on both wings
    """
    c_pass = call_result.get("overall_pass", False)
    p_pass = put_result.get("overall_pass", False)
    c_err  = bool(call_result.get("error"))
    p_err  = bool(put_result.get("error"))

    if c_pass and p_pass:
        return "GREEN"
    if c_pass or p_pass:
        return "YELLOW"
    if c_err and p_err:
        return "GREY"

    c_spread_fail = not call_result.get("pass_spread", True) and not c_err
    p_spread_fail = not put_result.get("pass_spread", True) and not p_err
    if c_spread_fail or p_spread_fail:
        return "RED"

    return "GREY"


def rank_tickers(rows: list) -> list:
    """
    Sort order:
      1. Color bucket: GREEN → YELLOW → RED → GREY
      2. Within bucket: avg(call_spread_pct, put_spread_pct) ascending
      3. Tiebreak: total open interest descending
    """
    color_order = {"GREEN": 0, "YELLOW": 1, "RED": 2, "GREY": 3}

    def _key(row):
        bucket = color_order.get(row.get("color", "GREY"), 3)
        c = row.get("call") or {}
        p = row.get("put")  or {}
        c_sp = c.get("spread_pct") or 999.0
        p_sp = p.get("spread_pct") or 999.0
        avg_spread = (c_sp + p_sp) / 2.0
        c_oi = c.get("openInterest") or 0.0
        p_oi = p.get("openInterest") or 0.0
        total_oi = -(c_oi + p_oi)  # negative → descending tiebreak
        return (bucket, avg_spread, total_oi)

    return sorted(rows, key=_key)
