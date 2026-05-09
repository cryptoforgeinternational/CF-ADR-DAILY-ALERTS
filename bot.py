"""
ATOM — Market Intelligence System
Powered by Cryptoforge Council
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
TELEGRAM_BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID     = os.getenv("TELEGRAM_CHAT_ID",   "YOUR_CHAT_ID_HERE")
COUNCIL_CHANNEL_ID   = -1003900611424
COUNCIL_INVITE_LINK  = "https://t.me/+ht1V0nEXDwk0YzI1"

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
log = logging.getLogger("ATOM")

_last_alerts: dict = {}
_subscribed_users: set = set()  # Users who enabled Live Trade Updates

def _cooldown_key(pair, tf, level_name, alert_type):
    return f"{pair}_{tf}_{level_name}_{alert_type}"

def _is_cooled_down(key):
    if key not in _last_alerts:
        return True
    elapsed = (datetime.now(timezone.utc) - _last_alerts[key]).total_seconds() / 60
    return elapsed >= ALERT_COOLDOWN_MINUTES

def _mark_alert(key):
    _last_alerts[key] = datetime.now(timezone.utc)

# ─────────────────────────────────────────────
# TELEGRAM HELPERS
# ─────────────────────────────────────────────
def send_telegram(message: str, chat_id=None, reply_markup: dict = None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id or TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            log.error(f"Telegram error: {r.text}")
        else:
            log.info("Telegram message sent successfully")
    except Exception as e:
        log.error(f"Telegram send failed: {e}")

def answer_callback_query(callback_query_id: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_query_id}, timeout=10)
    except Exception as e:
        log.error(f"answerCallbackQuery failed: {e}")

def is_council_member(user_id: int) -> bool:
    """Check if a user is a member of the Cryptoforge Council channel."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getChatMember"
    payload = {"chat_id": COUNCIL_CHANNEL_ID, "user_id": user_id}
    try:
        r = requests.post(url, json=payload, timeout=10)
        data = r.json()
        if data.get("ok"):
            status = data["result"].get("status", "")
            return status in ("member", "administrator", "creator")
        return False
    except Exception as e:
        log.error(f"Membership check failed: {e}")
        return False

# ─────────────────────────────────────────────
# MENU BUILDERS
# ─────────────────────────────────────────────
def send_access_denied(chat_id):
    message = (
        "🚫 <b>Access Restricted.</b>\n\n"
        "ATOM is exclusively available to\n"
        "<b>Cryptoforge Council</b> members.\n\n"
        "Join The Council to get access."
    )
    markup = {
        "inline_keyboard": [[
            {"text": "🔗 Join The Council", "url": COUNCIL_INVITE_LINK}
        ]]
    }
    send_telegram(message, chat_id=chat_id, reply_markup=markup)

def send_welcome(chat_id):
    message = (
        "⚡ <b>Welcome to ATOM</b>\n"
        "<i>Powered by Cryptoforge Council.</i>\n\n"
        "Your intelligent market partner is ready.\n"
        "Please select an option below:"
    )
    markup = {
        "inline_keyboard": [
            [{"text": "📊 #LiveTradeUpdates", "callback_data": "menu_live_trade"}],
            [{"text": "📰 #LiveNewsUpdates",  "callback_data": "menu_coming_soon"}],
            [{"text": "📅 #MarketPrep",        "callback_data": "menu_coming_soon"}],
            [{"text": "📈 #SwingTradeUpdates", "callback_data": "menu_coming_soon"}],
        ]
    }
    send_telegram(message, chat_id=chat_id, reply_markup=markup)

def send_live_trade_menu(chat_id, user_id: int):
    enabled = user_id in _subscribed_users
    status_text = (
        "✅ Alerts are currently <b>enabled</b>."
        if enabled else
        "❌ Alerts are currently <b>disabled</b>."
    )
    message = (
        "📊 <b>Live Trade Updates</b> 🔔\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Receive real-time trade updates based on our\n"
        "CX3 strategy on:\n\n"
        "• BTCUSDT, ETHUSDT, SOLUSDT, DOGEUSDT, 1000PEPEUSDT\n"
        "• Timeframes: 15m, 30m\n"
        "• Exchange: Bybit Futures\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{status_text}"
    )
    markup = {
        "inline_keyboard": [
            [
                {"text": "Enable Alerts ✅",  "callback_data": "alerts_enable"},
                {"text": "Disable Alerts ❌", "callback_data": "alerts_disable"},
            ],
            [{"text": "⬅️ Back to Menu", "callback_data": "menu_main"}],
        ]
    }
    send_telegram(message, chat_id=chat_id, reply_markup=markup)

def send_coming_soon(chat_id):
    message = (
        "🔒 <b>Coming Soon!</b>\n\n"
        "This feature is currently under development.\n"
        "Stay tuned for updates. 🚀"
    )
    markup = {
        "inline_keyboard": [[
            {"text": "⬅️ Back to Menu", "callback_data": "menu_main"}
        ]]
    }
    send_telegram(message, chat_id=chat_id, reply_markup=markup)

# ─────────────────────────────────────────────
# UPDATE HANDLER (polling)
# ─────────────────────────────────────────────
_last_update_id = 0

def get_updates():
    global _last_update_id
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"offset": _last_update_id + 1, "timeout": 10}
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if data.get("ok"):
            return data.get("result", [])
    except Exception as e:
        log.error(f"getUpdates failed: {e}")
    return []

def handle_updates():
    global _last_update_id
    updates = get_updates()
    for update in updates:
        _last_update_id = update["update_id"]

        # ── /start command ──
        if "message" in update:
            msg     = update["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg["from"]["id"]
            text    = msg.get("text", "")

            if text.strip() == "/start":
                log.info(f"User {user_id} started ATOM")
                if is_council_member(user_id):
                    send_welcome(chat_id)
                else:
                    send_access_denied(chat_id)

        # ── Button presses ──
        elif "callback_query" in update:
            cb      = update["callback_query"]
            chat_id = cb["message"]["chat"]["id"]
            user_id = cb["from"]["id"]
            data    = cb.get("data", "")
            cb_id   = cb["id"]

            answer_callback_query(cb_id)

            if not is_council_member(user_id):
                send_access_denied(chat_id)
                continue

            if data == "menu_main":
                send_welcome(chat_id)

            elif data == "menu_live_trade":
                send_live_trade_menu(chat_id, user_id)

            elif data == "menu_coming_soon":
                send_coming_soon(chat_id)

            elif data == "alerts_enable":
                _subscribed_users.add(user_id)
                log.info(f"User {user_id} enabled ATOM alerts")
                send_telegram(
                    "✅ <b>Live Trade Alerts Enabled!</b>\n\n"
                    "ATOM will notify you whenever the market\n"
                    "reaches or reacts at an ADR level. 📊",
                    chat_id=chat_id,
                    reply_markup={"inline_keyboard": [[
                        {"text": "⬅️ Back to Menu", "callback_data": "menu_main"}
                    ]]}
                )

            elif data == "alerts_disable":
                _subscribed_users.discard(user_id)
                log.info(f"User {user_id} disabled ATOM alerts")
                send_telegram(
                    "❌ <b>Live Trade Alerts Disabled.</b>\n\n"
                    "You will no longer receive market updates.\n"
                    "You can re-enable anytime from the menu.",
                    chat_id=chat_id,
                    reply_markup={"inline_keyboard": [[
                        {"text": "⬅️ Back to Menu", "callback_data": "menu_main"}
                    ]]}
                )

# ─────────────────────────────────────────────
# BYBIT DATA FETCHER
# ─────────────────────────────────────────────
def fetch_candles(symbol: str, interval: str, limit: int = 50) -> list[dict]:
    url = f"{BYBIT_BASE}/v5/market/kline"
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ATOM/1.0)",
        "Accept": "application/json",
    }
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("retCode") != 0:
        raise Exception(f"Bybit API error: {data.get('retMsg')}")
    raw = data["result"]["list"]
    candles = []
    for r in reversed(raw):
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
# ADR CALCULATOR
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

def price_is_near_any_level(candle, levels, adr_range):
    level_map = [
        ("ADR High", levels["adr10_high"], "resistance"),
        ("ADR High", levels["adr5_high"],  "resistance"),
        ("ADR Low",  levels["adr5_low"],   "support"),
        ("ADR Low",  levels["adr10_low"],  "support"),
    ]
    for level_name, level_price, zone in level_map:
        touched = (
            is_near_level(candle["high"],  level_price, adr_range) or
            is_near_level(candle["low"],   level_price, adr_range) or
            is_near_level(candle["close"], level_price, adr_range) or
            candle["low"] <= level_price <= candle["high"]
        )
        if touched:
            return level_name, level_price, zone
    return None

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

def get_pattern_at_level(prev, curr, zone):
    if zone == "resistance":
        if detect_bearish_engulfing(prev, curr):
            return "Bearish Engulfing", "reversal"
        if detect_shooting_star(curr):
            return "Shooting Star", "reversal"
        if detect_doji(curr):
            return "Doji", "reversal"
        if curr["close"] > max(prev["high"], curr["open"]):
            return "Breakout Candle", "breakout"
    elif zone == "support":
        if detect_bullish_engulfing(prev, curr):
            return "Bullish Engulfing", "reversal"
        if detect_hammer(curr):
            return "Hammer", "reversal"
        if detect_doji(curr):
            return "Doji", "reversal"
        if curr["close"] < min(prev["low"], curr["open"]):
            return "Breakdown Candle", "breakdown"
    return None

# ─────────────────────────────────────────────
# PROFESSIONAL ALERT TEMPLATES
# ─────────────────────────────────────────────
def build_proximity_alert(symbol, tf, zone):
    zone_emoji = "🔴" if zone == "resistance" else "🟢"
    return (
        f"📊 <b>ATOM Live Market Update</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔔 <b>{symbol}</b> is reaching its ADR {'High' if zone == 'resistance' else 'Low'}.\n"
        f"📈 Timeframe: {tf}\n"
        f"🏦 Exchange: Bybit Futures\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{zone_emoji} Zone: {'Resistance' if zone == 'resistance' else 'Support'}\n"
        f"⚡ <i>Time to have a look!</i>"
    )

def build_pattern_alert(symbol, tf, zone, pattern, signal):
    if signal == "reversal":
        action_line  = "👀 Watch closely for a potential <b>reversal!</b>"
        signal_emoji = "⚠️"
    elif signal == "breakout":
        action_line  = "👀 Watch closely for a potential <b>breakout!</b>"
        signal_emoji = "🚀"
    elif signal == "breakdown":
        action_line  = "👀 Watch closely for a potential <b>breakdown!</b>"
        signal_emoji = "🔻"
    else:
        action_line  = "👀 Watch closely for the next move!"
        signal_emoji = "⚠️"

    return (
        f"📊 <b>ATOM Live Trade Update</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{signal_emoji} <b>{symbol}</b> — {tf} {pattern} forming on ADR {'High' if zone == 'resistance' else 'Low'}.\n"
        f"🏦 Exchange: Bybit Futures\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{action_line}"
    )

# ─────────────────────────────────────────────
# BROADCAST TO SUBSCRIBED USERS
# ─────────────────────────────────────────────
def broadcast(message: str):
    if not _subscribed_users:
        log.info("No subscribed users — skipping broadcast.")
        return
    for user_id in _subscribed_users:
        send_telegram(message, chat_id=user_id)

# ─────────────────────────────────────────────
# SCANNER
# ─────────────────────────────────────────────
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

    curr = candles[-2]
    prev = candles[-3]

    result = price_is_near_any_level(curr, levels, adr_range)
    if not result:
        return

    level_name, level_price, zone = result
    pattern_result = get_pattern_at_level(prev, curr, zone)

    if pattern_result:
        pattern_name, signal = pattern_result
        key = _cooldown_key(symbol, tf_label, level_name, f"pattern_{pattern_name}")
        if _is_cooled_down(key):
            msg = build_pattern_alert(symbol, tf_label, zone, pattern_name, signal)
            log.info(f"PATTERN ALERT: {symbol} {tf_label} | {level_name} | {pattern_name}")
            broadcast(msg)
            _mark_alert(key)
    else:
        key = _cooldown_key(symbol, tf_label, level_name, "proximity")
        if _is_cooled_down(key):
            msg = build_proximity_alert(symbol, tf_label, zone)
            log.info(f"PROXIMITY ALERT: {symbol} {tf_label} | {level_name}")
            broadcast(msg)
            _mark_alert(key)

async def run_scan_cycle():
    tasks = [
        scan_pair(symbol, tf_label, tf_interval)
        for symbol in PAIRS
        for tf_label, tf_interval in TIMEFRAMES.items()
    ]
    await asyncio.gather(*tasks)

# ─────────────────────────────────────────────
# MAIN LOOPS
# ─────────────────────────────────────────────
async def poll_updates():
    """Continuously poll Telegram for user interactions."""
    while True:
        handle_updates()
        await asyncio.sleep(2)

async def market_scanner():
    """Scan markets every 15 minutes."""
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

async def main():
    log.info("=" * 50)
    log.info("  ATOM — Market Intelligence System")
    log.info("  Powered by Cryptoforge Council")
    log.info(f"  Pairs:      {', '.join(PAIRS)}")
    log.info(f"  Timeframes: {', '.join(TIMEFRAMES.keys())}")
    log.info(f"  Exchange:   Bybit Futures")
    log.info("=" * 50)

    send_telegram(
        "⚡ <b>ATOM is Online</b>\n"
        "<i>Powered by Cryptoforge Council</i>\n\n"
        f"Monitoring: {', '.join(PAIRS)}\n"
        f"Timeframes: {', '.join(TIMEFRAMES.keys())}\n"
        "Exchange: Bybit Futures\n\n"
        "ATOM is watching the markets..."
    )

    await asyncio.gather(
        poll_updates(),
        market_scanner(),
    )

if __name__ == "__main__":
    asyncio.run(main())
