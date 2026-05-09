"""
CX3 Cryptaluxe - ADR Alert Bot
Monitors Bybit perpetual pairs for ADR level touches + candlestick patterns
Sends Telegram notifications only — no auto-trading
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from pybit.unified_trading import HTTP
import requests

# ─────────────────────────────────────────────
# CONFIGURATION — Edit these values
# ─────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "YOUR_CHAT_ID_HERE")

PAIRS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "1000PEPEUSDT",
    "DOGEUSDT",
]

TIMEFRAMES = ["15", "30"]   # minutes

# How close to the ADR level (as % of ADR range) counts as "at the level"
LEVEL_PROXIMITY_PCT = 0.003   # 0.3% — adjust tighter/looser as needed

# Cooldown: don't re-alert same pair+timeframe+level+pattern within N minutes
ALERT_COOLDOWN_MINUTES = 60

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ADR_BOT")

# ─────────────────────────────────────────────
# BYBIT CLIENT (public, no API key needed)
# ─────────────────────────────────────────────
client = HTTP(testnet=False)

# ─────────────────────────────────────────────
# ALERT COOLDOWN TRACKER
# ─────────────────────────────────────────────
_last_alerts: dict = {}   # key -> datetime

def _cooldown_key(pair, tf, level_name, pattern):
    return f"{pair}_{tf}_{level_name}_{pattern}"

def _is_cooled_down(key):
    if key not in _last_alerts:
        return True
    elapsed = (datetime.now(timezone.utc) - _last_alerts[key]).total_seconds() / 60
    return elapsed >= ALERT_COOLDOWN_MINUTES

def _mark_alert(key):
    _last_alerts[key] = datetime.now(timezone.utc)


# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────
def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            log.error(f"Telegram error: {r.text}")
    except Exception as e:
        log.error(f"Telegram send failed: {e}")


# ─────────────────────────────────────────────
# BYBIT DATA FETCHER
# ─────────────────────────────────────────────
def fetch_candles(symbol: str, interval: str, limit: int = 50) -> list[dict]:
    """
    Returns candles as list of dicts: {open, high, low, close, volume, ts}
    Sorted oldest → newest.
    interval: "15" or "30" for intraday; "D" for daily
    """
    resp = client.get_kline(
        category="linear",
        symbol=symbol,
        interval=interval,
        limit=limit,
    )
    raw = resp["result"]["list"]
    candles = []
    for r in reversed(raw):   # Bybit returns newest first
        candles.append({
            "ts":     int(r[0]),
            "open":   float(r[1]),
            "high":   float(r[2]),
            "low":    float(r[3]),
            "close":  float(r[4]),
            "volume": float(r[5]),
        })
    return candles


# ─────────────────────────────────────────────
# ADR CALCULATOR  (mirrors your Pine Script)
# ─────────────────────────────────────────────
def calculate_adr_levels(symbol: str) -> dict | None:
    """
    Replicates CX3 Pine Script logic:
      adr_10 = avg of last 10 daily ranges
      adr_5  = avg of last 5  daily ranges
      ADR High = Today's Open + (adr / 2)
      ADR Low  = Today's Open - (adr / 2)
    Returns dict with keys: open, adr10_high, adr10_low, adr5_high, adr5_low
    """
    try:
        daily = fetch_candles(symbol, "D", limit=15)
        if len(daily) < 11:
            log.warning(f"{symbol}: not enough daily candles")
            return None

        today_open = daily[-1]["open"]

        # daily[0...-1] are completed days; daily[-1] is today (in progress)
        completed = daily[:-1]   # last element is today's open candle

        ranges = [c["high"] - c["low"] for c in completed]

        adr_10 = sum(ranges[-10:]) / 10
        adr_5  = sum(ranges[-5:])  / 5

        return {
            "open":      today_open,
            "adr10_high": today_open + adr_10 / 2,
            "adr10_low":  today_open - adr_10 / 2,
            "adr5_high":  today_open + adr_5  / 2,
            "adr5_low":   today_open - adr_5  / 2,
        }
    except Exception as e:
        log.error(f"{symbol} ADR calc error: {e}")
        return None


def is_near_level(price: float, level: float, adr_range: float) -> bool:
    """True if price is within LEVEL_PROXIMITY_PCT of the level."""
    threshold = adr_range * LEVEL_PROXIMITY_PCT
    return abs(price - level) <= threshold


# ─────────────────────────────────────────────
# CANDLESTICK PATTERN DETECTORS
# ─────────────────────────────────────────────
def candle_body(c):
    return abs(c["close"] - c["open"])

def candle_range(c):
    return c["high"] - c["low"]

def upper_wick(c):
    return c["high"] - max(c["open"], c["close"])

def lower_wick(c):
    return min(c["open"], c["close"]) - c["low"]

def is_bearish(c):
    return c["close"] < c["open"]

def is_bullish(c):
    return c["close"] > c["open"]


def detect_doji(c) -> bool:
    """Body is ≤ 10% of total range."""
    r = candle_range(c)
    if r == 0:
        return False
    return candle_body(c) / r <= 0.10


def detect_hammer(c) -> bool:
    """
    Bullish reversal at support:
    - Lower wick ≥ 2× body
    - Small upper wick (≤ body)
    - Body in upper 40% of range
    """
    body = candle_body(c)
    if body == 0:
        return False
    lw = lower_wick(c)
    uw = upper_wick(c)
    return lw >= 2 * body and uw <= body


def detect_shooting_star(c) -> bool:
    """
    Bearish reversal at resistance:
    - Upper wick ≥ 2× body
    - Small lower wick (≤ body)
    """
    body = candle_body(c)
    if body == 0:
        return False
    uw = upper_wick(c)
    lw = lower_wick(c)
    return uw >= 2 * body and lw <= body


def detect_bullish_engulfing(prev, curr) -> bool:
    """
    curr (bullish) body fully engulfs prev (bearish) body.
    """
    return (
        is_bearish(prev)
        and is_bullish(curr)
        and curr["open"] <= prev["close"]
        and curr["close"] >= prev["open"]
    )


def detect_bearish_engulfing(prev, curr) -> bool:
    """
    curr (bearish) body fully engulfs prev (bullish) body.
    """
    return (
        is_bullish(prev)
        and is_bearish(curr)
        and curr["open"] >= prev["close"]
        and curr["close"] <= prev["open"]
    )


def detect_breakout_above(candles: list[dict], level: float) -> bool:
    """Last closed candle closed above resistance level."""
    c = candles[-2]   # last fully closed candle
    return c["close"] > level


def detect_breakdown_below(candles: list[dict], level: float) -> bool:
    """Last closed candle closed below support level."""
    c = candles[-2]
    return c["close"] < level


# ─────────────────────────────────────────────
# PATTERN SCAN
# ─────────────────────────────────────────────
def scan_patterns_at_level(
    candles: list[dict],
    level: float,
    level_name: str,
    zone: str,           # "resistance" or "support"
    adr_range: float,
) -> list[str]:
    """
    Returns list of pattern names detected at the level on the last closed candle.
    """
    if len(candles) < 3:
        return []

    curr  = candles[-2]   # last fully closed candle
    prev  = candles[-3]   # candle before that

    # Check if the candle's body/wick actually touched the level zone
    touched = (
        is_near_level(curr["high"], level, adr_range)
        or is_near_level(curr["low"], level, adr_range)
        or is_near_level(curr["close"], level, adr_range)
        or (curr["low"] <= level <= curr["high"])
    )

    if not touched:
        return []

    patterns = []

    if zone == "resistance":
        if detect_doji(curr):
            patterns.append("🔴 Doji")
        if detect_shooting_star(curr):
            patterns.append("🔴 Shooting Star")
        if detect_bearish_engulfing(prev, curr):
            patterns.append("🔴 Bearish Engulfing")
        if detect_breakout_above(candles, level):
            patterns.append("🟡 Breakout Above Resistance")

    elif zone == "support":
        if detect_doji(curr):
            patterns.append("🟢 Doji")
        if detect_hammer(curr):
            patterns.append("🟢 Hammer")
        if detect_bullish_engulfing(prev, curr):
            patterns.append("🟢 Bullish Engulfing")
        if detect_breakdown_below(candles, level):
            patterns.append("🟡 Breakdown Below Support")

    return patterns


# ─────────────────────────────────────────────
# ALERT MESSAGE BUILDER
# ─────────────────────────────────────────────
def build_message(symbol, tf, level_name, zone, pattern, levels, candle):
    emoji_zone = "🔴 RESISTANCE" if zone == "resistance" else "🟢 SUPPORT"
    time_str = datetime.now(timezone.utc).strftime("%H:%M UTC")

    msg = (
        f"<b>⚡ CX3 ADR ALERT</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>Pair:</b>      {symbol}\n"
        f"<b>TF:</b>        {tf}m\n"
        f"<b>Zone:</b>      {emoji_zone}\n"
        f"<b>Level:</b>     {level_name}  ({levels[level_name]:.4f})\n"
        f"<b>Pattern:</b>   {pattern}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>Candle:</b>  O {candle['open']:.4f}  H {candle['high']:.4f}\n"
        f"           L {candle['low']:.4f}  C {candle['close']:.4f}\n"
        f"<b>Daily Open:</b> {levels['open']:.4f}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {time_str}\n"
        f"<i>Check chart manually before entering.</i>"
    )
    return msg


# ─────────────────────────────────────────────
# MAIN SCAN LOOP
# ─────────────────────────────────────────────
async def scan_pair(symbol: str, tf: str):
    log.info(f"Scanning {symbol} {tf}m ...")

    levels = calculate_adr_levels(symbol)
    if not levels is None and levels:
        adr_range = levels["adr10_high"] - levels["adr10_low"]
    else:
        return

    candles = fetch_candles(symbol, tf, limit=50)
    if len(candles) < 3:
        return

    # Define the four levels and their zones
    level_map = {
        "ADR10 High": (levels["adr10_high"], "resistance"),
        "ADR5 High":  (levels["adr5_high"],  "resistance"),
        "ADR5 Low":   (levels["adr5_low"],   "support"),
        "ADR10 Low":  (levels["adr10_low"],  "support"),
    }

    for level_name, (level_price, zone) in level_map.items():
        patterns = scan_patterns_at_level(
            candles, level_price, level_name, zone, adr_range
        )
        for pattern in patterns:
            key = _cooldown_key(symbol, tf, level_name, pattern)
            if _is_cooled_down(key):
                curr_candle = candles[-2]
                levels_for_msg = {**levels, level_name: level_price}
                msg = build_message(symbol, tf, level_name, zone, pattern, levels_for_msg, curr_candle)
                log.info(f"ALERT: {symbol} {tf}m | {level_name} | {pattern}")
                send_telegram(msg)
                _mark_alert(key)


async def run_scan_cycle():
    """Run one full scan across all pairs and timeframes."""
    tasks = [
        scan_pair(symbol, tf)
        for symbol in PAIRS
        for tf in TIMEFRAMES
    ]
    await asyncio.gather(*tasks)


async def scheduler():
    """
    Waits until the next candle close (15m or 30m boundary) then scans.
    Runs continuously.
    """
    log.info("=" * 50)
    log.info("  CX3 ADR Alert Bot — Started")
    log.info(f"  Pairs:      {', '.join(PAIRS)}")
    log.info(f"  Timeframes: {', '.join(TIMEFRAMES)}m")
    log.info("=" * 50)
    send_telegram(
        "✅ <b>CX3 ADR Bot Started</b>\n"
        f"Monitoring: {', '.join(PAIRS)}\n"
        f"Timeframes: {', '.join(tf+'m' for tf in TIMEFRAMES)}\n"
        "Waiting for ADR level touches..."
    )

    while True:
        now = datetime.now(timezone.utc)
        # Run a scan immediately on startup, then every 15 minutes
        await run_scan_cycle()

        # Sleep until next 15-minute mark
        minutes_past = now.minute % 15
        seconds_past = now.second
        sleep_seconds = (15 - minutes_past) * 60 - seconds_past
        if sleep_seconds <= 0:
            sleep_seconds = 15 * 60
        log.info(f"Next scan in {sleep_seconds // 60}m {sleep_seconds % 60}s")
        await asyncio.sleep(sleep_seconds)


if __name__ == "__main__":
    asyncio.run(scheduler())
