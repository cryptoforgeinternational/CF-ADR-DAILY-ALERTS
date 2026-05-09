# CX3 ADR Alert Bot — Complete Setup Guide

---

## What This Bot Does
- Monitors BTCUSDT, ETHUSDT, SOLUSDT, 1000PEPEUSDT, DOGEUSDT on Bybit Futures
- Calculates your ADR levels every 15 minutes (same formula as your Pine Script)
- Detects: Bearish Engulfing, Shooting Star, Doji at resistance | Bullish Engulfing, Hammer, Doji at support
- Detects breakouts above and breakdowns below your ADR levels
- Sends a Telegram notification when any pattern forms at a level
- Runs 24/7 in the cloud for free — no PC required

---

## STEP 1 — Create Your Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send the message: `/newbot`
3. Give it a name, e.g. `CX3 ADR Bot`
4. Give it a username, e.g. `cx3_adr_alert_bot` (must end in `bot`)
5. BotFather will give you a **token** like:
   ```
   7123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
   → Save this. This is your `TELEGRAM_BOT_TOKEN`

6. Now get your Chat ID:
   - Search for **@userinfobot** on Telegram
   - Start a chat with it
   - It will reply with your **ID** number like `123456789`
   → Save this. This is your `TELEGRAM_CHAT_ID`

7. Start a chat with your new bot (search for it, press START)

---

## STEP 2 — Deploy to Railway (Free Cloud Hosting)

Railway gives you free cloud compute. The bot runs 24/7 without your PC.

### 2a. Create a GitHub account (if you don't have one)
Go to https://github.com and sign up free.

### 2b. Create a new repository
1. Click **New Repository**
2. Name it `cx3-adr-bot`
3. Set it to **Private**
4. Click **Create Repository**

### 2c. Upload the bot files
Upload these 3 files to your repository:
- `bot.py`
- `requirements.txt`
- `Procfile`

(You can drag and drop them on the GitHub website)

### 2d. Deploy on Railway
1. Go to https://railway.app
2. Sign up with your GitHub account
3. Click **New Project** → **Deploy from GitHub repo**
4. Select your `cx3-adr-bot` repository
5. Railway will detect the Procfile automatically

### 2e. Set Environment Variables (Your Secrets)
In Railway, go to your project → **Variables** tab → Add these:

| Variable Name        | Value                          |
|----------------------|--------------------------------|
| `TELEGRAM_BOT_TOKEN` | `7123456789:AAFxxxxxxxxxxxx`   |
| `TELEGRAM_CHAT_ID`   | `123456789`                    |

Click **Deploy** — the bot starts running!

---

## STEP 3 — Verify It's Working

Within a few seconds of deploying, you should receive a Telegram message:

```
✅ CX3 ADR Bot Started
Monitoring: BTCUSDT, ETHUSDT, SOLUSDT, 1000PEPEUSDT, DOGEUSDT
Timeframes: 15m, 30m
Waiting for ADR level touches...
```

If you see this message — the bot is live and monitoring. ✅

---

## What Alerts Look Like

```
⚡ CX3 ADR ALERT
━━━━━━━━━━━━━━━━━━
Pair:      BTCUSDT
TF:        15m
Zone:      🔴 RESISTANCE
Level:     ADR10 High  (68420.5000)
Pattern:   🔴 Bearish Engulfing
━━━━━━━━━━━━━━━━━━
Candle:  O 68380.0  H 68510.0
         L 68200.0  C 68150.0
Daily Open: 67800.0000
━━━━━━━━━━━━━━━━━━
🕐 09:30 UTC
Check chart manually before entering.
```

---

## Customizing the Bot

Open `bot.py` and find the CONFIGURATION section at the top:

### Add or remove pairs:
```python
PAIRS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "1000PEPEUSDT",
    "DOGEUSDT",
    "BNBUSDT",     # ← add any Bybit perpetual pair here
]
```

### Adjust level sensitivity:
```python
LEVEL_PROXIMITY_PCT = 0.003   # 0.3% proximity to level triggers a check
# Increase to 0.005 to trigger earlier (wider zone)
# Decrease to 0.001 to trigger only when price is very close
```

### Change alert cooldown:
```python
ALERT_COOLDOWN_MINUTES = 60   # Won't re-alert same pattern on same level for 60 min
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| No startup message | Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in Railway variables |
| Bot crashes | Check Railway logs tab for error messages |
| Too many alerts | Increase `LEVEL_PROXIMITY_PCT` or `ALERT_COOLDOWN_MINUTES` |
| Too few alerts | Decrease `LEVEL_PROXIMITY_PCT` |
| Want to add a pair | Add its symbol string to the `PAIRS` list |

---

## Running Locally (Optional)

If you want to test on your own PC first:

```bash
# Install Python 3.11+ from python.org first, then:

pip install pybit requests

# Set your tokens (Windows):
set TELEGRAM_BOT_TOKEN=your_token_here
set TELEGRAM_CHAT_ID=your_chat_id_here

# Set your tokens (Mac/Linux):
export TELEGRAM_BOT_TOKEN=your_token_here
export TELEGRAM_CHAT_ID=your_chat_id_here

# Run:
python bot.py
```

---

## File Summary

| File | Purpose |
|---|---|
| `bot.py` | The main bot — all logic lives here |
| `requirements.txt` | Python packages Railway installs automatically |
| `Procfile` | Tells Railway to run `bot.py` as a background worker |
| `SETUP_GUIDE.md` | This file |
