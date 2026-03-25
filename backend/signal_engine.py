
"""
SignalPro FX — MT5 Real-Time Signal Engine v3.0
=================================================
✅ FREE real-time data — MT5 ka apna Python library
✅ Koi third-party API nahi chahiye
✅ Twelve Data ki zarurat KHATAM
✅ Tick-level data, live prices, direct broker connection

Requirements:
  pip install MetaTrader5 pandas numpy

MT5 Setup:
  1. MetaTrader 5 install karo (broker se)
  2. MT5 open rakho jab script chale
  3. Tools → Options → Expert Advisors →
       ✅ Allow algorithmic trading
       ✅ Allow DLL imports
"""

import os
import time
import json
import logging
import requests
from datetime import datetime
from typing import Optional

import pandas as pd
import numpy as np

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: pip install MetaTrader5")
    exit(1)

# ─────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("signalpro_mt5.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("SignalPro-MT5")

# ─────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
CHANNEL_ID         = os.getenv("TELEGRAM_CHANNEL",   "@your_channel")

# MT5 login (optional — agar auto login chahiye)
# Warna MT5 already open hoga to yeh blank chhod do
MT5_LOGIN    = 0          # Broker account number (0 = already logged in)
MT5_PASSWORD = ""         # Broker password
MT5_SERVER   = ""         # Broker server name

PAIRS = {
    "XAU/USD": {"symbol": "XAUUSD", "pip": 0.1,   "htf1": mt5.TIMEFRAME_H1,  "htf2": mt5.TIMEFRAME_H4,  "ltf": mt5.TIMEFRAME_M15},
    "EUR/USD": {"symbol": "EURUSD", "pip": 0.0001, "htf1": mt5.TIMEFRAME_H1,  "htf2": mt5.TIMEFRAME_H4,  "ltf": mt5.TIMEFRAME_M15},
    "GBP/USD": {"symbol": "GBPUSD", "pip": 0.0001, "htf1": mt5.TIMEFRAME_H1,  "htf2": mt5.TIMEFRAME_H4,  "ltf": mt5.TIMEFRAME_M15},
    "USD/JPY": {"symbol": "USDJPY", "pip": 0.01,   "htf1": mt5.TIMEFRAME_H1,  "htf2": mt5.TIMEFRAME_H4,  "ltf": mt5.TIMEFRAME_M15},
    "GBP/JPY": {"symbol": "GBPJPY", "pip": 0.01,   "htf1": mt5.TIMEFRAME_H1,  "htf2": mt5.TIMEFRAME_H4,  "ltf": mt5.TIMEFRAME_M15},
    "EUR/JPY": {"symbol": "EURJPY", "pip": 0.01,   "htf1": mt5.TIMEFRAME_H1,  "htf2": mt5.TIMEFRAME_H4,  "ltf": mt5.TIMEFRAME_M15},
}

MIN_SCORE       = 70
SIGNAL_COOLDOWN = 60    # minutes
TP_RR_RATIO     = 2.0


# ═══════════════════════════════════════════════════════
# MT5 CONNECTION MANAGER
# ═══════════════════════════════════════════════════════
class MT5Manager:
    """MT5 se connect karna aur data fetch karna"""

    def __init__(self):
        self.connected = False

    def connect(self) -> bool:
        """MT5 se connect karo"""
        if not mt5.initialize():
            logger.error(f"MT5 initialize failed: {mt5.last_error()}")
            return False

        # Agar login credentials diye hain
        if MT5_LOGIN and MT5_PASSWORD and MT5_SERVER:
            if not mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER):
                logger.error(f"MT5 login failed: {mt5.last_error()}")
                return False
            logger.info(f"MT5 logged in: account {MT5_LOGIN}")
        else:
            # Already open MT5 use karo
            info = mt5.account_info()
            if info:
                logger.info(f"MT5 connected: {info.server} | Account: {info.login} | Balance: {info.balance}")
            else:
                logger.warning("MT5 connected but no account info — demo mode")

        self.connected = True
        return True

    def disconnect(self):
        mt5.shutdown()
        self.connected = False
        logger.info("MT5 disconnected")

    def get_candles(self, symbol: str, timeframe: int, count: int = 150) -> Optional[pd.DataFrame]:
        """MT5 se OHLCV candles lo — REAL TIME"""
        if not self.connected:
            logger.error("MT5 not connected")
            return None

        # Symbol available hai check karo
        if not mt5.symbol_select(symbol, True):
            logger.warning(f"Symbol {symbol} not available: {mt5.last_error()}")
            return None

        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)

        if rates is None or len(rates) == 0:
            logger.warning(f"No data for {symbol} tf={timeframe}: {mt5.last_error()}")
            return None

        df = pd.DataFrame(rates)
        df["time"]  = pd.to_datetime(df["time"], unit="s")
        df.rename(columns={
            "time":    "datetime",
            "tick_volume": "volume"
        }, inplace=True)

        # Columns sahi order mein
        df = df[["datetime", "open", "high", "low", "close", "volume"]].copy()
        return df

    def get_live_price(self, symbol: str) -> Optional[dict]:
        """Current live bid/ask price"""
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return {
            "bid":    tick.bid,
            "ask":    tick.ask,
            "spread": round((tick.ask - tick.bid) * 10000, 1),
            "time":   datetime.fromtimestamp(tick.time).strftime("%H:%M:%S"),
        }

    def get_symbol_info(self, symbol: str) -> Optional[dict]:
        """Symbol ki details"""
        info = mt5.symbol_info(symbol)
        if info is None:
            return None
        return {
            "digits":     info.digits,
            "point":      info.point,
            "spread":     info.spread,
            "trade_mode": info.trade_mode,
        }

    def check_connection(self) -> bool:
        """Connection alive hai check karo"""
        if mt5.terminal_info() is None:
            logger.warning("MT5 connection lost — reconnecting...")
            self.connected = False
            return self.connect()
        return True


# ═══════════════════════════════════════════════════════
# INDICATORS
# ═══════════════════════════════════════════════════════
class Indicators:

    @staticmethod
    def ema(s: pd.Series, p: int) -> pd.Series:
        return s.ewm(span=p, adjust=False).mean()

    @staticmethod
    def atr(high, low, close, p=14) -> pd.Series:
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs()
        ], axis=1).max(axis=1)
        return tr.ewm(span=p, adjust=False).mean()

    @staticmethod
    def rsi(s: pd.Series, p=14) -> pd.Series:
        d = s.diff()
        g = d.clip(lower=0).ewm(com=p-1, adjust=False).mean()
        l = (-d.clip(upper=0)).ewm(com=p-1, adjust=False).mean()
        return 100 - 100 / (1 + g / l)

IND = Indicators()


# ═══════════════════════════════════════════════════════
# 7-STEP FILTER SYSTEM
# ═══════════════════════════════════════════════════════

def step1_htf_trend(df_1h, df_4h) -> dict:
    """Step 1: HTF Trend — 1H + 4H EMA20/30 filter | 25 pts"""
    result = {"score": 0, "direction": None, "detail": ""}

    if df_1h is None or df_4h is None or len(df_1h) < 35 or len(df_4h) < 35:
        result["detail"] = "HTF data missing"
        return result

    for label, df in [("1H", df_1h), ("4H", df_4h)]:
        close = df["close"]
        ema20 = IND.ema(close, 20).iloc[-1]
        ema30 = IND.ema(close, 30).iloc[-1]
        price = close.iloc[-1]
        bull  = price > ema20 and price > ema30
        bear  = price < ema20 and price < ema30
        if not bull and not bear:
            result["detail"] = f"{label}: Price between EMAs — mixed trend"
            return result

    close_4h = df_4h["close"]
    p4h      = close_4h.iloc[-1]
    ema20_4h = IND.ema(close_4h, 20).iloc[-1]

    result["direction"] = "BUY" if p4h > ema20_4h else "SELL"
    result["score"]     = 25
    result["detail"]    = f"HTF aligned {result['direction']} (1H+4H EMA20/30)"
    return result


def step2_setup_detection(df_ltf, direction) -> dict:
    """Step 2: Breakout / Pullback / Retest | 15 pts"""
    result = {"score": 0, "setup": None, "detail": ""}
    if df_ltf is None or len(df_ltf) < 30:
        result["detail"] = "LTF data insufficient"
        return result

    close = df_ltf["close"]
    high  = df_ltf["high"]
    low   = df_ltf["low"]
    price = close.iloc[-1]

    recent_high = high.iloc[-21:-1].max()
    recent_low  = low.iloc[-21:-1].min()
    atr_val     = IND.atr(high, low, close).iloc[-1]
    buf         = atr_val * 0.3

    if direction == "BUY":
        breakout = price > recent_high - buf
        pullback = high.iloc[-8:-2].max() > recent_high * 0.998 and close.iloc[-3] < close.iloc[-1]
        mid      = (recent_high + recent_low) / 2
        retest   = low.iloc[-5:-1].min() <= mid + buf and price > mid
    else:
        breakout = price < recent_low  + buf
        pullback = low.iloc[-8:-2].min() < recent_low * 1.002 and close.iloc[-3] > close.iloc[-1]
        mid      = (recent_high + recent_low) / 2
        retest   = high.iloc[-5:-1].max() >= mid - buf and price < mid

    if breakout:
        result.update({"setup": "BREAKOUT", "score": 15,
            "detail": f"Breakout {'above' if direction=='BUY' else 'below'} structure"})
    elif pullback:
        result.update({"setup": "PULLBACK", "score": 15,
            "detail": "Pullback after structure break"})
    elif retest:
        result.update({"setup": "RETEST",   "score": 15,
            "detail": f"Retest of mid-zone {mid:.5f}"})
    else:
        result["detail"] = "No setup found"
    return result


def step3_smc(df_ltf, direction) -> dict:
    """Step 3: SMC — Liquidity Sweep + Order Block + FVG | 20 pts"""
    result = {"score": 0, "liquidity_sweep": False,
              "order_block": False, "fvg": False, "detail": ""}
    if df_ltf is None or len(df_ltf) < 10:
        return result

    close = df_ltf["close"]
    high  = df_ltf["high"]
    low   = df_ltf["low"]
    open_ = df_ltf["open"]

    prev_high  = high.iloc[-10:-2].max()
    prev_low   = low.iloc[-10:-2].min()
    curr_high  = high.iloc[-1]
    curr_low   = low.iloc[-1]
    curr_close = close.iloc[-1]

    # Liquidity Sweep
    if direction == "BUY" and curr_low < prev_low and curr_close > prev_low:
        result["liquidity_sweep"] = True
        result["detail"] += "💧 Liq.Sweep ✓ | "
    elif direction == "SELL" and curr_high > prev_high and curr_close < prev_high:
        result["liquidity_sweep"] = True
        result["detail"] += "💧 Liq.Sweep ✓ | "

    # Order Block
    avg_body = (close - open_).abs().iloc[-20:].mean()
    for i in range(-6, -1):
        body     = abs(close.iloc[i] - open_.iloc[i])
        is_strong = body > avg_body * 1.2
        if direction == "BUY" and is_strong and close.iloc[i] < open_.iloc[i] and curr_close > high.iloc[i]:
            result["order_block"] = True
            result["detail"] += f"🏦 OB@{high.iloc[i]:.4f} ✓ | "
            break
        elif direction == "SELL" and is_strong and close.iloc[i] > open_.iloc[i] and curr_close < low.iloc[i]:
            result["order_block"] = True
            result["detail"] += f"🏦 OB@{low.iloc[i]:.4f} ✓ | "
            break

    # FVG
    for i in range(-5, -2):
        if direction == "BUY":
            gap = low.iloc[i+1] - high.iloc[i-1]
            if gap > 0:
                result["fvg"]    = True
                result["detail"] += f"⚡ FVG {gap:.4f} ✓ | "
                break
        else:
            gap = low.iloc[i-1] - high.iloc[i+1]
            if gap > 0:
                result["fvg"]    = True
                result["detail"] += f"⚡ FVG {gap:.4f} ✓ | "
                break

    smc_count = sum([result["liquidity_sweep"], result["order_block"], result["fvg"]])
    if smc_count == 0:
        result["detail"] = "No SMC confluence"
        return result

    result["score"]  = 20
    result["detail"] = result["detail"].rstrip(" | ")
    return result


def step4_ema_alignment(df_ltf, direction) -> dict:
    """Step 4: EMA 5>10>20>30 chain | 15 pts"""
    result = {"score": 0, "detail": ""}
    if df_ltf is None:
        return result

    close = df_ltf["close"]
    e5  = IND.ema(close, 5).iloc[-1]
    e10 = IND.ema(close, 10).iloc[-1]
    e20 = IND.ema(close, 20).iloc[-1]
    e30 = IND.ema(close, 30).iloc[-1]

    aligned = (e5 > e10 > e20 > e30) if direction == "BUY" else (e5 < e10 < e20 < e30)

    if aligned:
        result["score"]  = 15
        result["detail"] = f"EMA 5/10/20/30 {'bullish' if direction=='BUY' else 'bearish'} stack ✓"
    else:
        result["detail"] = f"EMA mixed: {e5:.4f} {e10:.4f} {e20:.4f} {e30:.4f}"
    return result


def step5_candle(df_ltf, direction) -> dict:
    """Step 5: Engulfing / Pin Bar / Strong Rejection | 15 pts"""
    result = {"score": 0, "pattern": None, "detail": ""}
    if df_ltf is None or len(df_ltf) < 3:
        return result

    o  = df_ltf["open"].iloc[-1];  c  = df_ltf["close"].iloc[-1]
    h  = df_ltf["high"].iloc[-1];  l  = df_ltf["low"].iloc[-1]
    o2 = df_ltf["open"].iloc[-2];  c2 = df_ltf["close"].iloc[-2]

    body         = abs(c - o)
    candle_range = h - l
    if candle_range == 0:
        result["detail"] = "Doji"
        return result

    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    body_ratio = body / candle_range
    avg_body   = (df_ltf["close"] - df_ltf["open"]).abs().iloc[-10:].mean()

    engulfing = False
    pin_bar   = False
    rejection = False

    if direction == "BUY":
        engulfing = c2 < o2 and c > o and c > o2 and o < c2 and body > avg_body
        pin_bar   = lower_wick > body * 2 and lower_wick > upper_wick * 2 and body_ratio < 0.35
        rejection = c > o and body_ratio > 0.6 and body > avg_body * 1.3
    else:
        engulfing = c2 > o2 and c < o and c < o2 and o > c2 and body > avg_body
        pin_bar   = upper_wick > body * 2 and upper_wick > lower_wick * 2 and body_ratio < 0.35
        rejection = c < o and body_ratio > 0.6 and body > avg_body * 1.3

    if engulfing:
        result.update({"pattern": "ENGULFING", "score": 15,
            "detail": f"{'Bullish' if direction=='BUY' else 'Bearish'} engulfing ✓"})
    elif pin_bar:
        result.update({"pattern": "PIN_BAR", "score": 15,
            "detail": f"Pin bar ({'lower' if direction=='BUY' else 'upper'} wick) ✓"})
    elif rejection:
        result.update({"pattern": "STRONG_REJECTION", "score": 15,
            "detail": f"Strong rejection candle ✓"})
    else:
        result["detail"] = f"No pattern (body_ratio={body_ratio:.2f})"
    return result


def step6_levels(df_ltf, direction, pip) -> dict:
    """Step 6: Entry / SL (swing) / TP (1:2 min) auto calculate"""
    close = df_ltf["close"]
    high  = df_ltf["high"]
    low   = df_ltf["low"]

    price    = close.iloc[-1]
    atr_val  = IND.atr(high, low, close).iloc[-1]
    swing_h  = high.iloc[-20:].max()
    swing_l  = low.iloc[-20:].min()

    if direction == "BUY":
        entry = price
        sl    = round(swing_l - atr_val * 0.5, 5)
        risk  = max(entry - sl, atr_val)
        tp1   = round(entry + risk * TP_RR_RATIO,       5)
        tp2   = round(entry + risk * TP_RR_RATIO * 1.5, 5)
    else:
        entry = price
        sl    = round(swing_h + atr_val * 0.5, 5)
        risk  = max(sl - entry, atr_val)
        tp1   = round(entry - risk * TP_RR_RATIO,       5)
        tp2   = round(entry - risk * TP_RR_RATIO * 1.5, 5)

    return {
        "entry":     round(entry, 5),
        "sl":        round(sl,    5),
        "tp1":       tp1,
        "tp2":       tp2,
        "risk_pips": round(risk / pip, 1),
        "rr_ratio":  round(abs(tp1 - entry) / risk, 2),
    }


def step7_score(s1, s2, s3, s4, s5) -> dict:
    """Step 7: Final score — signal tabhi bhejo jab >= 70%"""
    total   = s1["score"] + s2["score"] + s3["score"] + s4["score"] + s5["score"]
    pct     = round(total / 90 * 100, 1)
    return {
        "HTF Trend":     s1["score"],
        "Setup":         s2["score"],
        "SMC":           s3["score"],
        "EMA Alignment": s4["score"],
        "Candle":        s5["score"],
        "total":  total,
        "max":    90,
        "pct":    pct,
        "passed": pct >= MIN_SCORE,
    }


# ═══════════════════════════════════════════════════════
# MAIN ENGINE
# ═══════════════════════════════════════════════════════
class SignalProMT5:

    def __init__(self):
        self.mt5      = MT5Manager()
        self.last_sig = {}

    def start(self):
        if not self.mt5.connect():
            logger.error("MT5 connect failed — MT5 khula hai? Login sahi hai?")
            return False
        logger.info("MT5 connected ✅")
        return True

    def analyze_pair(self, name: str, config: dict) -> Optional[dict]:
        sym = config["symbol"]
        logger.info(f"  [{sym}] Fetching data...")

        df_1h  = self.mt5.get_candles(sym, config["htf1"], 100)
        df_4h  = self.mt5.get_candles(sym, config["htf2"], 80)
        df_ltf = self.mt5.get_candles(sym, config["ltf"],  150)
        tick   = self.mt5.get_live_price(sym)

        if df_ltf is None:
            logger.warning(f"  [{sym}] No LTF data")
            return None

        # Live price log karo
        if tick:
            logger.info(f"  [{sym}] Live: Bid={tick['bid']} Ask={tick['ask']} Spread={tick['spread']}pts")

        # 7 Steps
        s1 = step1_htf_trend(df_1h, df_4h)
        if not s1["score"]:
            logger.info(f"  [{sym}] ❌ S1: {s1['detail']}")
            return None
        direction = s1["direction"]
        logger.info(f"  [{sym}] ✅ S1: {s1['detail']}")

        s2 = step2_setup_detection(df_ltf, direction)
        if not s2["score"]:
            logger.info(f"  [{sym}] ❌ S2: {s2['detail']}")
            return None
        logger.info(f"  [{sym}] ✅ S2: {s2['detail']}")

        s3 = step3_smc(df_ltf, direction)
        if not s3["score"]:
            logger.info(f"  [{sym}] ❌ S3: {s3['detail']}")
            return None
        logger.info(f"  [{sym}] ✅ S3: {s3['detail']}")

        s4 = step4_ema_alignment(df_ltf, direction)
        if not s4["score"]:
            logger.info(f"  [{sym}] ❌ S4: {s4['detail']}")
            return None
        logger.info(f"  [{sym}] ✅ S4: {s4['detail']}")

        s5 = step5_candle(df_ltf, direction)
        if not s5["score"]:
            logger.info(f"  [{sym}] ❌ S5: {s5['detail']}")
            return None
        logger.info(f"  [{sym}] ✅ S5: {s5['detail']}")

        levels = step6_levels(df_ltf, direction, config["pip"])
        score  = step7_score(s1, s2, s3, s4, s5)

        logger.info(f"  [{sym}] 📊 Score: {score['pct']}% — {'✅ PASS' if score['passed'] else '❌ FAIL'}")
        if not score["passed"]:
            return None

        # Live price use karo agar available hai
        if tick:
            entry = tick["ask"] if direction == "BUY" else tick["bid"]
            levels["entry"] = round(entry, 5)

        return {
            "pair":       name,
            "symbol":     sym,
            "direction":  direction,
            "entry":      levels["entry"],
            "tp1":        levels["tp1"],
            "tp2":        levels["tp2"],
            "sl":         levels["sl"],
            "risk_pips":  levels["risk_pips"],
            "rr_ratio":   levels["rr_ratio"],
            "score_pct":  score["pct"],
            "score_breakdown": score,
            "setup":      s2.get("setup"),
            "smc": {
                "liquidity_sweep": s3["liquidity_sweep"],
                "order_block":     s3["order_block"],
                "fvg":             s3["fvg"],
            },
            "candle_pattern": s5.get("pattern"),
            "spread":     tick["spread"] if tick else None,
            "timestamp":  datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "interval":   "M15",
            "data_source": "MT5 Real-Time",
        }

    def send_telegram(self, sig: dict):
        smc   = sig["smc"]
        score = sig["score_breakdown"]
        arrow = "🟢" if sig["direction"] == "BUY" else "🔴"

        smc_str = " | ".join(filter(None, [
            "💧 Liq.Sweep" if smc["liquidity_sweep"] else "",
            "🏦 OB"         if smc["order_block"]     else "",
            "⚡ FVG"        if smc["fvg"]              else "",
        ])) or "—"

        spread_str = f"{sig['spread']}pts" if sig.get("spread") else "—"

        msg = (
            f"{arrow} *{sig['pair']} — {sig['direction']} SIGNAL*\n"
            f"{'─'*32}\n\n"
            f"📍 *Entry:*    `{sig['entry']}`\n"
            f"✅ *TP1:*      `{sig['tp1']}`\n"
            f"✅ *TP2:*      `{sig['tp2']}`\n"
            f"❌ *SL:*       `{sig['sl']}`\n"
            f"📐 *R:R:*      1:{sig['rr_ratio']}\n"
            f"📏 *Risk:*     {sig['risk_pips']} pips\n"
            f"📶 *Spread:*   {spread_str}\n\n"
            f"{'─'*32}\n"
            f"📊 *Score:*    {sig['score_pct']}%\n"
            f"🔧 *Setup:*    {sig['setup']}\n"
            f"🕯 *Candle:*   {sig['candle_pattern']}\n"
            f"🏦 *SMC:*      {smc_str}\n\n"
            f"*Breakdown:*\n"
            f"  HTF Trend:     `{score['HTF Trend']}/25`\n"
            f"  Setup:         `{score['Setup']}/15`\n"
            f"  SMC:           `{score['SMC']}/20`\n"
            f"  EMA Alignment: `{score['EMA Alignment']}/15`\n"
            f"  Candle:        `{score['Candle']}/15`\n\n"
            f"📡 *Source:* MT5 Real-Time\n"
            f"⏰ `{sig['timestamp']}`  TF: M15\n\n"
            f"⚠️ _Risk management karo — max 1-2% per trade_"
        )

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            r = requests.post(url, json={
                "chat_id": CHANNEL_ID, "text": msg, "parse_mode": "Markdown"
            }, timeout=10)
            if r.status_code == 200:
                logger.info(f"✅ Telegram sent: {sig['pair']} {sig['direction']} {sig['score_pct']}%")
            else:
                logger.error(f"Telegram error: {r.text}")
        except Exception as e:
            logger.error(f"Telegram failed: {e}")

    def should_send(self, pair: str) -> bool:
        last = self.last_sig.get(pair)
        if not last:
            return True
        return (datetime.utcnow() - last).seconds / 60 >= SIGNAL_COOLDOWN

    def run_once(self):
        logger.info("═" * 55)
        logger.info(f"SCAN: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

        if not self.mt5.check_connection():
            logger.error("MT5 reconnect failed — scan skipped")
            return []

        found = []
        for name, config in PAIRS.items():
            try:
                sig = self.analyze_pair(name, config)
                if sig and self.should_send(name):
                    self.send_telegram(sig)
                    self.last_sig[name] = datetime.utcnow()
                    found.append(sig)
                    with open("signals_history.json", "a") as f:
                        f.write(json.dumps({
                            k: v for k, v in sig.items()
                            if k != "score_breakdown"
                        }) + "\n")
            except Exception as e:
                logger.error(f"{name} error: {e}")
            time.sleep(0.5)   # MT5 throttle — no API limits!

        logger.info(f"Scan done — Signals found: {len(found)}")
        return found

    def run_forever(self, interval_min=15):
        logger.info("SignalPro MT5 v3 — Starting")
        logger.info(f"Pairs: {list(PAIRS.keys())}")
        logger.info(f"Min Score: {MIN_SCORE}% | Scan: {interval_min}min")

        if not self.start():
 return

        try:
            while True:
                try:
                    self.run_once()
                except Exception as e:
                    logger.error(f"Scan error: {e}")
                logger.info(f"Next scan in {interval_min} min...")
                time.sleep(interval_min * 60)
        except KeyboardInterrupt:
            logger.info("Stopped by user")
        finally:
            self.mt5.disconnect()


# ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SignalPro MT5 Engine")
    parser.add_argument("--once",     action="store_true", help="Sirf ek scan")
    parser.add_argument("--interval", type=int, default=15, help="Scan interval minutes")
    parser.add_argument("--score",    type=int, default=MIN_SCORE, help="Min score %")
    args = parser.parse_args()

    if args.score != MIN_SCORE:
        MIN_SCORE = args.score

    engine = SignalProMT5()

    if args.once:
        if engine.start():
            engine.run_once()
            engine.mt5.disconnect()
    else:
        engine.run_forever(interval_min=args.interval)
