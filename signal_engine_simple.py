"""
SignalPro FX — GitHub Actions Signal Engine
============================================
Yeh file GitHub Actions pe directly chalti hai.
Koi VPS nahi chahiye — GitHub FREE mein run karta hai!

Environment variables se config leta hai (GitHub Secrets):
  TWELVE_DATA_API_KEY
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHANNEL
"""

import os
import requests
import json
from datetime import datetime

# ─────────────────────────────────────────────
# CONFIG — GitHub Secrets se automatically aata hai
# ─────────────────────────────────────────────
API_KEY  = os.environ.get("TWELVE_DATA_API_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_CHANNEL", "")

PAIRS = [
    {"symbol": "XAU/USD", "name": "Gold",    "pip": 0.1},
    {"symbol": "EUR/USD", "name": "EUR/USD", "pip": 0.0001},
    {"symbol": "GBP/USD", "name": "GBP/USD", "pip": 0.0001},
    {"symbol": "USD/JPY", "name": "USD/JPY", "pip": 0.01},
]

SIGNAL_MIN_SCORE = 55   # Is score se kam pe signal nahi bhejenge


# ─────────────────────────────────────────────
# PRICE DATA
# ─────────────────────────────────────────────
def get_candles(symbol, interval="15min", count=100):
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol":     symbol,
        "interval":   interval,
        "outputsize": count,
        "apikey":     API_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if "values" not in data:
            print(f"  API error for {symbol}: {data.get('message','unknown')}")
            return None
        values = data["values"]
        closes = [float(v["close"]) for v in reversed(values)]
        highs  = [float(v["high"])  for v in reversed(values)]
        lows   = [float(v["low"])   for v in reversed(values)]
        return {"close": closes, "high": highs, "low": lows}
    except Exception as e:
        print(f"  Fetch error for {symbol}: {e}")
        return None


# ─────────────────────────────────────────────
# INDICATORS
# ─────────────────────────────────────────────
def ema(data, period):
    k = 2 / (period + 1)
    result = [data[0]]
    for price in data[1:]:
        result.append(price * k + result[-1] * (1 - k))
    return result

def rsi(data, period=14):
    gains, losses = [], []
    for i in range(1, len(data)):
        diff = data[i] - data[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    if len(gains) < period:
        return 50
    avg_g = sum(gains[-period:]) / period
    avg_l = sum(losses[-period:]) / period
    if avg_l == 0:
        return 100
    rs = avg_g / avg_l
    return 100 - (100 / (1 + rs))

def macd(data, fast=12, slow=26, sig=9):
    macd_line = [f - s for f, s in zip(ema(data, fast), ema(data, slow))]
    sig_line  = ema(macd_line, sig)
    histogram = [m - s for m, s in zip(macd_line, sig_line)]
    return macd_line, sig_line, histogram

def atr(highs, lows, closes, period=14):
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i]  - closes[i-1])
        )
        trs.append(tr)
    return sum(trs[-period:]) / period if len(trs) >= period else trs[-1]

def bollinger(data, period=20, std_dev=2):
    if len(data) < period:
        return data[-1], data[-1], data[-1]
    window  = data[-period:]
    mid     = sum(window) / period
    std     = (sum((x - mid)**2 for x in window) / period) ** 0.5
    return mid + std * std_dev, mid, mid - std * std_dev


# ─────────────────────────────────────────────
# SIGNAL LOGIC
# ─────────────────────────────────────────────
def analyze(candles, pair):
    closes = candles["close"]
    highs  = candles["high"]
    lows   = candles["low"]

    if len(closes) < 55:
        return None

    e8  = ema(closes, 8)
    e21 = ema(closes, 21)
    e50 = ema(closes, 50)
    r   = rsi(closes)
    _, _, hist = macd(closes)
    bb_u, bb_m, bb_l = bollinger(closes)
    atr_v = atr(highs, lows, closes)

    p      = closes[-1]
    buy_score  = 0
    sell_score = 0

    # BUY conditions
    if e8[-1] > e21[-1] > e50[-1]:              buy_score += 30
    if r < 60:                                   buy_score += 20
    if hist[-1] > 0 and hist[-1] > hist[-2]:     buy_score += 25
    if p < bb_m + (bb_u - bb_m) * 0.3:          buy_score += 25

    # SELL conditions
    if e8[-1] < e21[-1] < e50[-1]:              sell_score += 30
    if r > 40:                                   sell_score += 20
    if hist[-1] < 0 and hist[-1] < hist[-2]:    sell_score += 25
    if p > bb_m - (bb_m - bb_l) * 0.3:         sell_score += 25

    if buy_score >= SIGNAL_MIN_SCORE and buy_score > sell_score:
        direction = "BUY"
        score     = buy_score
        tp1 = round(p + atr_v * 2.0, 5)
        tp2 = round(p + atr_v * 3.0, 5)
        sl  = round(p - atr_v * 1.0, 5)
    elif sell_score >= SIGNAL_MIN_SCORE and sell_score > buy_score:
        direction = "SELL"
        score     = sell_score
        tp1 = round(p - atr_v * 2.0, 5)
        tp2 = round(p - atr_v * 3.0, 5)
        sl  = round(p + atr_v * 1.0, 5)
    else:
        return None

    return {
        "pair":      pair["symbol"],
        "direction": direction,
        "entry":     round(p, 5),
        "tp1":       tp1,
        "tp2":       tp2,
        "sl":        sl,
        "score":     score,
        "rsi":       round(r, 1),
        "time":      datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }


# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────
def send_telegram(signal):
    if not TG_TOKEN or not TG_CHAT:
        print("  Telegram config missing — check GitHub Secrets!")
        return False

    arrow = "🟢" if signal["direction"] == "BUY" else "🔴"
    msg = (
        f"{arrow} *{signal['pair']} — {signal['direction']}*\n\n"
        f"📍 Entry:  `{signal['entry']}`\n"
        f"✅ TP1:   `{signal['tp1']}`\n"
        f"✅ TP2:   `{signal['tp2']}`\n"
        f"❌ SL:    `{signal['sl']}`\n\n"
        f"📊 RSI: {signal['rsi']} | Strength: {signal['score']}%\n"
        f"⏰ {signal['time']}\n\n"
        f"⚠️ _Risk manage karo — 1-2% per trade_\n"
        f"📈 _SignalPro FX_"
    )
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id":    TG_CHAT,
            "text":       msg,
            "parse_mode": "Markdown"
        }, timeout=10)
        if r.status_code == 200:
            print(f"  ✅ Telegram pe bheja: {signal['pair']} {signal['direction']}")
            return True
        else:
            print(f"  ❌ Telegram error: {r.text}")
            return False
    except Exception as e:
        print(f"  ❌ Send failed: {e}")
        return False


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    print(f"\n{'='*50}")
    print(f"SignalPro FX — GitHub Actions Run")
    print(f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*50}\n")

    if not API_KEY:
        print("ERROR: TWELVE_DATA_KEY secret set nahi hai!")
        print("Repo → Settings → Secrets → Actions → New secret")
        return

    signals_found = 0

    for pair in PAIRS:
        print(f"Checking {pair['symbol']}...")
        candles = get_candles(pair["symbol"])

        if candles is None:
            print(f"  Skip — data nahi mila")
            continue

        signal = analyze(candles, pair)

        if signal:
            print(f"  SIGNAL: {signal['direction']} @ {signal['entry']} (score: {signal['score']}%)")
            send_telegram(signal)
            signals_found += 1
        else:
            print(f"  No signal — market unclear")

    print(f"\n{'='*50}")
    print(f"Scan done! Signals found: {signals_found}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
