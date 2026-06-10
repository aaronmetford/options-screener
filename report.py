"""
report.py — write sortable HTML report and flat CSV.
No I/O outside the two public functions write_html() and write_csv().
"""
import csv
import html as _html
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────────────

def _fmt(val, spec=".2f"):
    if val is None:
        return "—"
    try:
        return format(float(val), spec)
    except (TypeError, ValueError):
        return str(val)


def _pct(val):
    if val is None:
        return "—"
    try:
        return f"{float(val):.1%}"
    except (TypeError, ValueError):
        return str(val)


def _esc(s):
    return _html.escape(str(s)) if s is not None else ""


# ── CSS + sort JS (inlined, no CDN) ──────────────────────────────────────────

_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Options Screener — {date}</title>
<style>
  *{{box-sizing:border-box}}
  body{{font:13px/1.4 system-ui,sans-serif;margin:1em;background:#fff;color:#212529}}
  h1{{font-size:1.3em;margin:0 0 .5em}}
  h2{{font-size:1.1em;margin:1.5em 0 .4em;border-bottom:1px solid #dee2e6;padding-bottom:.2em}}
  .summary{{background:#f8f9fa;border:1px solid #dee2e6;border-radius:4px;
            padding:.5em 1em;margin-bottom:1em;line-height:2}}
  .chip{{display:inline-block;padding:1px 7px;border-radius:3px;font-size:11px;
         font-weight:700;white-space:nowrap}}
  .G{{background:#d4edda;color:#155724}}
  .Y{{background:#fff3cd;color:#856404}}
  .R{{background:#f8d7da;color:#721c24}}
  .X{{background:#e2e3e5;color:#383d41}}
  table{{border-collapse:collapse;width:100%;font-size:12px}}
  th,td{{border:1px solid #dee2e6;padding:3px 7px;white-space:nowrap}}
  th{{background:#343a40;color:#fff;cursor:pointer;user-select:none;text-align:center}}
  th:hover{{background:#495057}}
  td{{text-align:right}}
  td.left{{text-align:left}}
  tr:hover td{{filter:brightness(.94)}}
  .ok{{color:#155724;font-weight:700}}
  .fail{{color:#721c24}}
  section{{margin-top:1.5em}}
</style>
<script>
function sortTbl(id,col){{
  var tbl=document.getElementById(id),tb=tbl.tBodies[0];
  var rows=Array.from(tb.rows);
  var asc=tbl.dataset.sc==col&&tbl.dataset.sd=='a';
  rows.sort(function(a,b){{
    var av=a.cells[col].dataset.v??a.cells[col].textContent.trim();
    var bv=b.cells[col].dataset.v??b.cells[col].textContent.trim();
    var an=parseFloat(av),bn=parseFloat(bv);
    if(!isNaN(an)&&!isNaN(bn))return asc?bn-an:an-bn;
    return asc?bv.localeCompare(av):av.localeCompare(bv);
  }});
  rows.forEach(function(r){{tb.appendChild(r)}});
  tbl.dataset.sc=col;tbl.dataset.sd=asc?'d':'a';
}}
</script>
</head>
<body>
<h1>Options Liquidity Screener &mdash; {date}</h1>
"""

_TAIL = "</body></html>"

_COLS = [
    "Ticker", "Status", "Price",
    "Call Strike", "Call Exp", "Call Prem$", "Call Sprd$", "Call Sprd%", "Call OI",
    "Put Strike",  "Put Exp",  "Put Prem$",  "Put Sprd$",  "Put Sprd%",  "Put OI",
    "Avg Sprd%", "Notes",
]

_COLOR_CLASS = {"GREEN": "G", "YELLOW": "Y", "RED": "R", "GREY": "X"}
_COLOR_LABEL = {"GREEN": "GREEN", "YELLOW": "YELLOW", "RED": "RED", "GREY": "GREY/ERR"}
_ROW_STYLE   = {
    "GREEN":  "background:#d4edda",
    "YELLOW": "background:#fff3cd",
    "RED":    "background:#f8d7da",
    "GREY":   "background:#e9ecef",
}


# ── row builder ──────────────────────────────────────────────────────────────

def _side_td(s: dict, label: str) -> str:
    """Return <td> cells for one side (5 cells)."""
    if not s or s.get("error"):
        err = _esc((s or {}).get("error", "no data"))
        return (
            f'<td class="left fail" colspan="5">'
            f'<small>{label}: {err}</small></td>'
        )
    p_ok = s.get("pass_premium", False)
    sp_ok = s.get("pass_spread", False)
    pc = _fmt(s.get("premium_per_contract"), ".2f")
    sd = _fmt(s.get("spread_dollars"), ".3f")
    sp = _pct(s.get("spread_pct"))
    oi = _fmt(s.get("openInterest"), ".0f") if s.get("openInterest") is not None else "—"
    strike = _fmt(s.get("strike"), ".2f")
    exp = _esc(s.get("expiration") or "—")
    prem_cls = "ok" if p_ok  else "fail"
    sp_cls   = "ok" if sp_ok else "fail"
    return (
        f'<td>{strike}</td>'
        f'<td>{exp}</td>'
        f'<td class="{prem_cls}">${pc}</td>'
        f'<td class="{sp_cls}">{sd}</td>'
        f'<td class="{sp_cls}">{sp}</td>'
        f'<td>{oi}</td>'
    )


def _build_row(row: dict, idx: int) -> str:
    color   = row.get("color", "GREY")
    rstyle  = _ROW_STYLE.get(color, "")
    cls     = _COLOR_CLASS.get(color, "X")
    ticker  = _esc(row["ticker"])
    call    = row.get("call") or {}
    put     = row.get("put")  or {}
    und     = (call.get("underlyingPrice") or put.get("underlyingPrice"))
    und_str = f"${_fmt(und, '.2f')}" if und else "—"

    c_sp = call.get("spread_pct")
    p_sp = put.get("spread_pct")
    avg_sp = ((c_sp + p_sp) / 2.0) if (c_sp is not None and p_sp is not None) else None
    avg_sp_sort = avg_sp if avg_sp is not None else 999.0

    reasons = []
    for s, lbl in ((call, "C"), (put, "P")):
        for r in (s.get("fail_reasons") or []):
            reasons.append(f"{lbl}: {_esc(r)}")
    notes = " &nbsp;|&nbsp; ".join(reasons)

    return (
        f'<tr style="{rstyle}">'
        f'<td class="left" data-v="{idx}"><strong>{ticker}</strong></td>'
        f'<td><span class="chip {cls}">{_COLOR_LABEL[color]}</span></td>'
        f'<td>{und_str}</td>'
        + _side_td(call, "call")
        + _side_td(put,  "put")
        + f'<td data-v="{avg_sp_sort:.6f}">{_pct(avg_sp)}</td>'
        f'<td class="left"><small style="color:#666">{notes}</small></td>'
        f'</tr>'
    )


def _build_table(rows: list, table_id: str) -> str:
    ths = "".join(
        f'<th onclick="sortTbl(\'{table_id}\',{i})">{c}</th>'
        for i, c in enumerate(_COLS)
    )
    body = "".join(_build_row(r, i) for i, r in enumerate(rows))
    return (
        f'<table id="{table_id}" data-sc="" data-sd="a">'
        f'<thead><tr>{ths}</tr></thead>'
        f'<tbody>{body}</tbody></table>'
    )


# ── public API ───────────────────────────────────────────────────────────────

def write_html(
    rows: list,
    output_path: str,
    scan_date: str,
    total_tickers: int,
    total_requests: int,
    credits_info: str = "",
    color_counts: dict = None,
):
    color_counts = color_counts or {}
    green  = [r for r in rows if r.get("color") == "GREEN"]
    yellow = [r for r in rows if r.get("color") == "YELLOW"]
    red    = [r for r in rows if r.get("color") == "RED"]
    grey   = [r for r in rows if r.get("color") == "GREY"]

    megacap = [
        r for r in rows
        if (
            r.get("call", {}).get("underlyingPrice")
            or r.get("put", {}).get("underlyingPrice") or 0
        ) > 150
        and r.get("color") in ("GREEN", "YELLOW")
    ]

    cred_part = f" &nbsp;|&nbsp; {_esc(credits_info)}" if credits_info else ""
    summary = (
        f'<div class="summary">'
        f'<strong>Scan date:</strong> {scan_date} &nbsp;|&nbsp; '
        f'<strong>Tickers:</strong> {total_tickers} &nbsp;|&nbsp; '
        f'<strong>Requests:</strong> {total_requests}'
        f'{cred_part}'
        f' &nbsp;|&nbsp; '
        f'<span class="chip G">GREEN: {len(green)}</span> '
        f'<span class="chip Y">YELLOW: {len(yellow)}</span> '
        f'<span class="chip R">RED: {len(red)}</span> '
        f'<span class="chip X">GREY: {len(grey)}</span>'
        f'</div>'
    )

    parts = [_HEAD.format(date=scan_date), summary]

    if green or yellow:
        parts.append(
            '<section><h2>Liquid Options — Green &amp; Yellow</h2>'
            + _build_table(green + yellow, "tbl_main")
            + '</section>'
        )

    if red:
        parts.append(
            '<section><h2>Spread too wide — Red</h2>'
            + _build_table(red, "tbl_red")
            + '</section>'
        )

    if grey:
        parts.append(
            '<section><h2>No data / Error — Grey</h2>'
            + _build_table(grey, "tbl_grey")
            + '</section>'
        )

    if megacap:
        parts.append(
            '<section>'
            '<h2>Cheap Megacap Watch (underlying &gt; $150, one wing passes)</h2>'
            + _build_table(megacap, "tbl_mega")
            + '</section>'
        )

    parts.append(_TAIL)
    Path(output_path).write_text("".join(parts), encoding="utf-8")


def write_csv(rows: list, output_path: str):
    """One row per ticker with call_ and put_ prefixed columns."""
    if not rows:
        return

    flat: list[dict] = []
    for row in rows:
        rec: dict = {"ticker": row["ticker"], "color": row.get("color", "GREY")}
        for side in ("call", "put"):
            s = row.get(side) or {}
            for k, v in s.items():
                if k not in ("ticker", "side"):
                    rec[f"{side}_{k}"] = v
        flat.append(rec)

    fieldnames = list(dict.fromkeys(k for r in flat for k in r))  # order-preserving dedup
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(flat)
