"""
CX3 Cryptaluxe - ADR Alert Bot
Uses Bybit API from Singapore server
Sends Telegram notifications only — no auto-trading
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
import requests

# ─────────────────────────────────────────────
# CONFIGURATION
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

TIMEFRAMES = {"15m": "15", "30m": "30"}

LEVEL_PROXIMITY_PCT    = 0.003
ALERT_COOLDOWN_MINUTES = 60
BYBIT_BASE             = "https://api.bybit.com"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ADR_BOT")

_last_alerts: dict = {}

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
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            log.error(f"Telegram error: {r.text}")
        else:
            log.info("Telegram message sent successfully")
    except Exception as e:
        log.error(f"Telegram send failed: {e}")

# ─────────────────────────────────────────────
# BYBIT DATA FETCHER
# ─────────────────────────────────────────────
def fetch_candles(symbol: str, interval: str, limit: int = 50) -> list[dict]:
    """
    Fetch from Bybit v5 API.
    interval: '15', '30', 'D'
    """
    url = f"{BYBIT_BASE}/v5/market/kline"
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ADRBot/1.0)",
        "Accept": "application/json",
    }
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("retCode") != 0:
        raise Exception(f"Bybit API error: {data.get('retMsg')}")
    raw = data["result"]["list"]
    candles = []
    for r in reversed(raw):  # Bybit returns newest first
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
# ADR CALCULATOR (mirrors your Pine Script)
# ─────────────────────────────────────────────
def calculate_adr_levels(symbol: str) -> dict | None:
    try:
        daily = fetch_candles(symbol, "D", limit=15)
        if len(daily) < 11:
            log.warning(f"{symbol}: not enough daily candles")
            return None
        today_open = daily[-1]["open"]
        completed  = daily[:-1]
        ranges     = [c["high"] - c["low"] for c in completed]
        adr_10 = sum(ranges[-10:]) / 10
        adr_5  = sum(ranges[-5:])  / 5
        return {
            "open":       today_open,
            "adr10_high": today_open + adr_10 / 2,
            "adr10_low":  today_open - adr_10 / 2,
            "adr5_high":  today_open + adr_5  / 2,
            "adr5_low":   today_open - adr_5  / 2,
        }
    except Exception as e:
        log.error(f"{symbol} ADR calc error: {e}")
        return None

def is_near_level(price, level, adr_range):
    return abs(price - level) <= adr_range * LEVEL_PROXIMITY_PCT

# ─────────────────────────────────────────────
# CANDLESTICK DETECTORS
# ─────────────────────────────────────────────
def candle_body(c):  return abs(c["close"] - c["open"])
def candle_range(c): return c["high"] - c["low"]
def upper_wick(c):   return c["high"] - max(c["open"], c["close"])
def lower_wick(c):   return min(c["open"], c["close"]) - c["low"]
def is_bearish(c):   return c["close"] < c["open"]
def is_bullish(c):   return c["close"] > c["open"]

def detect_doji(c):
    r = candle_range(c)
    return r > 0 and candle_body(c) / r <= 0.10

def detect_hammer(c):
    body = candle_body(c)
    return body > 0 and lower_wick(c) >= 2 * body and upper_wick(c) <= body

def detect_shooting_star(c):
    body = candle_body(c)
    return body > 0 and upper_wick(c) >= 2 * body and lower_wick(c) <= body

def detect_bullish_engulfing(prev, curr):
    return (is_bearish(prev) and is_bullish(curr)
            and curr["open"] <= prev["close"] and curr["close"] >= prev["open"])

def detect_bearish_engulfing(prev, curr):
    return (is_bullish(prev) and is_bearish(curr)
            and curr["open"] >= prev["close"] and curr["close"] <= prev["open"])

def scan_patterns_at_level(candles, level, zone, adr_range):
    if len(candles) < 3:
        return []
    curr, prev = candles[-2], candles[-3]
    touched = (is_near_level(curr["high"],  level, adr_range)
               or is_near_level(curr["low"],   level, adr_range)
               or is_near_level(curr["close"], level, adr_range)
               or curr["low"] <= level <= curr["high"])
    if not touched:
        return []
    patterns = []
    if zone == "resistance":
        if detect_doji(curr):                    patterns.append("🔴 Doji")
        if detect_shooting_star(curr):           patterns.append("🔴 Shooting Star")
        if detect_bearish_engulfing(prev, curr): patterns.append("🔴 Bearish Engulfing")
        if curr["close"] > level:                patterns.append("🟡 Breakout Above Resistance")
    elif zone == "support":
        if detect_doji(curr):                    patterns.append("🟢 Doji")
        if detect_hammer(curr):                  patterns.append("🟢 Hammer")
        if detect_bullish_engulfing(prev, curr): patterns.append("🟢 Bullish Engulfing")
        if curr["close"] < level:                patterns.append("🟡 Breakdown Below Support")
    return patterns

def build_message(symbol, tf, level_name, zone, pattern, level_price, levels, candle):
    emoji_zone = "🔴 RESISTANCE" if zone == "resistance" else "🟢 SUPPORT"
    time_str = datetime.now(timezone.utc).strftime("%H:%M UTC")
    return (
        f"<b>⚡ CX3 ADR ALERT</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>Pair:</b>      {symbol}\n"
        f"<b>TF:</b>        {tf}\n"
        f"<b>Zone:</b>      {emoji_zone}\n"
        f"<b>Level:</b>     {level_name}  ({level_price:.4f})\n"
        f"<b>Pattern:</b>   {pattern}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>Candle:</b>  O {candle['open']:.4f}  H {candle['high']:.4f}\n"
        f"           L {candle['low']:.4f}  C {candle['close']:.4f}\n"
        f"<b>Daily Open:</b> {levels['open']:.4f}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {time_str}\n"
        f"<i>Check chart manually before entering.</i>"
    )

async def scan_pair(symbol: str, tf_label: str, tf_interval: str):
    log.info(f"Scanning {symbol} {tf_label} ...")
    levels = calculate_adr_levels(symbol)
    if not levels:
        return
    adr_range = levels["adr10_high"] - levels["adr10_low"]
    try:
        candles = fetch_candles(symbol, tf_interval, limit=50)
    except Exception as e:
        log.error(f"{symbol} {tf_label} candle fetch error: {e}")
        return
    if len(candles) < 3:
        return
    level_map = {
        "ADR10 High": (levels["adr10_high"], "resistance"),
        "ADR5 High":  (levels["adr5_high"],  "resistance"),
        "ADR5 Low":   (levels["adr5_low"],   "support"),
        "ADR10 Low":  (levels["adr10_low"],  "support"),
    }
    for level_name, (level_price, zone) in level_map.items():
        patterns = scan_patterns_at_level(candles, level_price, zone, adr_range)
        for pattern in patterns:
            key = _cooldown_key(symbol, tf_label, level_name, pattern)
            if _is_cooled_down(key):
                msg = build_message(symbol, tf_label, level_name, zone, pattern,
                                    level_price, levels, candles[-2])
                log.info(f"ALERT: {symbol} {tf_label} | {level_name} | {pattern}")
                send_telegram(msg)
                _mark_alert(key)

async def run_scan_cycle():
    tasks = [
        scan_pair(symbol, tf_label, tf_interval)
        for symbol in PAIRS
        for tf_label, tf_interval in TIMEFRAMES.items()
    ]
    await asyncio.gather(*tasks)

async def scheduler():
    log.info("=" * 50)
    log.info("  CX3 ADR Alert Bot — Started")
    log.info(f"  Pairs:      {', '.join(PAIRS)}")
    log.info(f"  Timeframes: {', '.join(TIMEFRAMES.keys())}")
    log.info(f"  Exchange:   Bybit Futures")
    log.info("=" * 50)
    send_telegram(
        "✅ <b>CX3 ADR Bot Started</b>\n"
        f"Monitoring: {', '.join(PAIRS)}\n"
        f"Timeframes: {', '.join(TIMEFRAMES.keys())}\n"
        "Exchange: Bybit Futures\n"
        "Waiting for ADR level touches..."
    )
    while True:
        await run_scan_cycle()
        now = datetime.now(timezone.utc)
        minutes_past = now.minute % 15
        seconds_past = now.second
        sleep_seconds = (15 - minutes_past) * 60 - seconds_past
        if sleep_seconds <= 0:
            sleep_seconds = 15 * 60
        log.info(f"Next scan in {sleep_seconds // 60}m {sleep_seconds % 60}s")
        await asyncio.sleep(sleep_seconds)

if __name__ == "__main__":
    asyncio.run(scheduler())
