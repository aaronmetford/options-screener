# All tuneable thresholds and limits live here.
# Edit this file to adjust screener behaviour without touching any other module.

# === Premium filter (dollars per contract = mid * 100) ===
MIN_PREMIUM = 7       # skip options cheaper than $7/contract (too illiquid to fill)
MAX_PREMIUM = 75      # skip options more expensive than $75/contract

# === Bid/ask spread filter ===
MAX_SPREAD_ABS = 0.05  # max spread in dollars (ask - bid)
MAX_SPREAD_PCT = 0.07  # max spread as fraction of mid (7%)

# === Open interest / volume liquidity filter ===
MIN_OI  = 1000   # minimum open interest for liquidity PASS
MIN_VOL = 500    # minimum daily volume for liquidity PASS (OR with OI)

# === Concurrency ===
MAX_WORKERS = 5  # ThreadPoolExecutor worker threads (tested safe on marketdata.app)

# === Request budget ===
# The screener aborts before calling the API if estimated requests exceed this.
# Each ticker costs 2 requests (call + put).
REQUEST_BUDGET = 300

# === Rate limiting ===
# marketdata.app free tier: ~100 req/min documented; paid tiers higher.
# Default conservative.  Raise once you know your plan limit.
REQUESTS_PER_MINUTE = 60

# === Optional underlying-price filter ===
# If underlyingPrice is returned by the API, drop tickers below this threshold.
# Set to 0 to disable.
MIN_STOCK_PRICE = 7.0

# === Retry / backoff ===
MAX_RETRIES  = 3    # attempts per request before giving up
BACKOFF_BASE = 2.0  # seconds; urllib3 doubles this on each retry
