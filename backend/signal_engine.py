"""
SignalPro FX -- MT5 Real-Time Signal Engine v3.1
Windows CMD compatible -- no emoji in logs
"""

import os
import sys
import time
import json
import logging
import requests
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import numpy as np

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: pip install MetaTrader5")
    sys.exit(1)

# ── Logging setup -- Windows CMD safe ──────────────────────────
class SafeFormatter(logging.Formatter):
    def format(self, record):
        msg = super().format(record)
        replacements = {
            "\u2705":"[OK]", "\u274c":"[NO]", "\u2550":"=",
            "\u2192":"->",   "\u2714":"OK",   "\u2716":"NO",
            "\u256c":"=",    "\u2502":"|",    "\u2500":"-",
        }
        for k, v in replacements.items():
            msg = msg.replace(k, v)
        try:
            msg.encode(sys.stdout.encoding or "utf-8")
        except (UnicodeEncodeError, LookupError):
            msg = msg.encode("ascii", "replace").decode("ascii")
        return msg

log_formatter = SafeFormatter("%(asctime)s | %(levelname)s | %(message)s")

file_handler = logging.FileHandler("signalpro_mt5.log", encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)

logger = logging.getLogger("SignalPro")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# ── CONFIG ──────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
CHANNEL_ID         = os.getenv("TELEGRAM_CHANNEL",   "@your_channel")

MT5_LOGIN    = 0
MT5_PASSWORD = ""
MT5_SERVER   = ""

PAIRS = {
    "XAU/USD": {"symbol":"XAUUSD", "pip":0.1,    "htf1":mt5.TIMEFRAME_H1, "htf2":mt5.TIMEFRAME_H4, "ltf":mt5.TIMEFRAME_M15},
    "EUR/USD": {"symbol":"EURUSD", "pip":0.0001,  "htf1":mt5.TIMEFRAME_H1, "htf2":mt5.TIMEFRAME_H4, "ltf":mt5.TIMEFRAME_M15},
    "GBP/USD": {"symbol":"GBPUSD", "pip":0.0001,  "htf1":mt5.TIMEFRAME_H1, "htf2":mt5.TIMEFRAME_H4, "ltf":mt5.TIMEFRAME_M15},
    "USD/JPY": {"symbol":"USDJPY", "pip":0.01,    "htf1":mt5.TIMEFRAME_H1, "htf2":mt5.TIMEFRAME_H4, "ltf":mt5.TIMEFRAME_M15},
    "GBP/JPY": {"symbol":"GBPJPY", "pip":0.01,    "htf1":mt5.TIMEFRAME_H1, "htf2":mt5.TIMEFRAME_H4, "ltf":mt5.TIMEFRAME_M15},
    "EUR/JPY": {"symbol":"EURJPY", "pip":0.01,    "htf1":mt5.TIMEFRAME_H1, "htf2":mt5.TIMEFRAME_H4, "ltf":mt5.TIMEFRAME_M15},
}

MIN_SCORE       = 70
SIGNAL_COOLDOWN = 60
TP_RR_RATIO     = 2.0


# ── MT5 MANAGER ─────────────────────────────────────────────────
class MT5Manager:
    def __init__(self):
        self.connected = False

    def connect(self):
        if not mt5.initialize():
            logger.error("MT5 initialize failed: %s", mt5.last_error())
            return False
        if MT5_LOGIN and MT5_PASSWORD and MT5_SERVER:
            if not mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER):
                logger.error("MT5 login failed: %s", mt5.last_error())
                return False
        info = mt5.account_info()
        if info:
            logger.info("MT5 connected: %s | Account: %s | Balance: %s",
                        info.server, info.login, info.balance)
        self.connected = True
        return True

    def disconnect(self):
        mt5.shutdown()
        self.connected = False

    def get_candles(self, symbol, timeframe, count=150):
        if not mt5.symbol_select(symbol, True):
            return None
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None or len(rates) == 0:
            return None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.rename(columns={"time":"datetime","tick_volume":"volume"}, inplace=True)
        return df[["datetime","open","high","low","close","volume"]].copy()

    def get_tick(self, symbol):
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return {"bid":tick.bid, "ask":tick.ask,
                "spread": round((tick.ask - tick.bid) / mt5.symbol_info(symbol).point)}

    def check_connection(self):
        if mt5.terminal_info() is None:
            self.connected = False
            return self.connect()
        return True


# ── INDICATORS ──────────────────────────────────────────────────
def ema(s, p):
    return s.ewm(span=p, adjust=False).mean()

def atr(high, low, close, p=14):
    tr = pd.concat([high-low,
                    (high-close.shift()).abs(),
                    (low-close.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(span=p, adjust=False).mean()


# ── STEP 1: HTF TREND ───────────────────────────────────────────
def step1_htf(df1h, df4h):
    r = {"score":0, "direction":None, "detail":""}
    if df1h is None or df4h is None or len(df1h)<35 or len(df4h)<35:
        r["detail"] = "HTF data missing"
        return r
    for label, df in [("1H", df1h), ("4H", df4h)]:
        c   = df["close"]
        e20 = ema(c, 20).iloc[-1]
        e30 = ema(c, 30).iloc[-1]
        p   = c.iloc[-1]
        if not ((p > e20 and p > e30) or (p < e20 and p < e30)):
            r["detail"] = "%s: Price between EMAs -- no clear trend" % label
            return r
    c4  = df4h["close"]
    p4  = c4.iloc[-1]
    e20 = ema(c4, 20).iloc[-1]
    r["direction"] = "BUY" if p4 > e20 else "SELL"
    r["score"]     = 25
    r["detail"]    = "HTF %s confirmed (1H+4H)" % r["direction"]
    return r


# ── STEP 2: SETUP DETECTION ─────────────────────────────────────
def step2_setup(df, direction):
    r = {"score":0, "setup":None, "detail":""}
    if df is None or len(df) < 30:
        r["detail"] = "Not enough data"
        return r

    c    = df["close"]
    h    = df["high"]
    l    = df["low"]
    p    = c.iloc[-1]
    atr_v = atr(h, l, c).iloc[-1]

    # Use last 15 candles for structure (less strict)
    rec_h = h.iloc[-16:-1].max()
    rec_l = l.iloc[-16:-1].min()
    buf   = atr_v * 0.5   # wider buffer

    if direction == "BUY":
        # Breakout: price near or above recent high
        if p >= rec_h - buf:
            r.update({"setup":"BREAKOUT","score":15,"detail":"Breakout above %.5f" % rec_h})
            return r
        # Pullback: recent candles went up then pulled back
        if h.iloc[-6:-1].max() > rec_h * 0.997:
            r.update({"setup":"PULLBACK","score":15,"detail":"Pullback in uptrend"})
            return r
        # Retest: price near middle of range
        mid = (rec_h + rec_l) / 2
        if abs(p - mid) < atr_v * 1.5:
            r.update({"setup":"RETEST","score":15,"detail":"Retest zone %.5f" % mid})
            return r
    else:
        if p <= rec_l + buf:
            r.update({"setup":"BREAKOUT","score":15,"detail":"Breakdown below %.5f" % rec_l})
            return r
        if l.iloc[-6:-1].min() < rec_l * 1.003:
            r.update({"setup":"PULLBACK","score":15,"detail":"Pullback in downtrend"})
            return r
        mid = (rec_h + rec_l) / 2
        if abs(p - mid) < atr_v * 1.5:
            r.update({"setup":"RETEST","score":15,"detail":"Retest zone %.5f" % mid})
            return r

    r["detail"] = "No setup (price in middle of range)"
    return r


# ── STEP 3: SMC ─────────────────────────────────────────────────
def step3_smc(df, direction):
    r = {"score":0,"liq_sweep":False,"order_block":False,"fvg":False,"detail":""}
    if df is None or len(df) < 10:
        return r

    c  = df["close"]
    h  = df["high"]
    l  = df["low"]
    o  = df["open"]

    ph = h.iloc[-12:-2].max()
    pl = l.iloc[-12:-2].min()

    # Liquidity sweep
    if direction == "BUY" and l.iloc[-1] < pl and c.iloc[-1] > pl:
        r["liq_sweep"] = True
        r["detail"] += "LiqSweep "
    elif direction == "SELL" and h.iloc[-1] > ph and c.iloc[-1] < ph:
        r["liq_sweep"] = True
        r["detail"] += "LiqSweep "

    # Order block
    avg_body = (c - o).abs().iloc[-20:].mean()
    for i in range(-7, -1):
        body = abs(c.iloc[i] - o.iloc[i])
        if body < avg_body * 1.0:
            continue
        if direction == "BUY" and c.iloc[i] < o.iloc[i] and c.iloc[-1] > h.iloc[i]:
            r["order_block"] = True
            r["detail"] += "OB@%.4f " % h.iloc[i]
            break
        if direction == "SELL" and c.iloc[i] > o.iloc[i] and c.iloc[-1] < l.iloc[i]:
            r["order_block"] = True
            r["detail"] += "OB@%.4f " % l.iloc[i]
            break

    # FVG
    for i in range(-6, -2):
        if direction == "BUY":
            gap = l.iloc[i+1] - h.iloc[i-1]
            if gap > 0:
                r["fvg"] = True
                r["detail"] += "FVG=%.5f " % gap
                break
        else:
            gap = l.iloc[i-1] - h.iloc[i+1]
            if gap > 0:
                r["fvg"] = True
                r["detail"] += "FVG=%.5f " % gap
                break

    smc_count = sum([r["liq_sweep"], r["order_block"], r["fvg"]])
    if smc_count == 0:
        r["detail"] = "No SMC confluence"
        return r
    r["score"] = 20
    return r


# ── STEP 4: EMA ALIGNMENT ───────────────────────────────────────
def step4_ema(df, direction):
    r = {"score":0,"detail":""}
    if df is None:
        return r
    c   = df["close"]
    e5  = ema(c,5).iloc[-1]
    e10 = ema(c,10).iloc[-1]
    e20 = ema(c,20).iloc[-1]
    e30 = ema(c,30).iloc[-1]
    ok  = (e5>e10>e20>e30) if direction=="BUY" else (e5<e10<e20<e30)
    if ok:
        r["score"]  = 15
        r["detail"] = "EMA 5/10/20/30 %s aligned" % direction
    else:
        r["detail"] = "EMA mixed: %.4f %.4f %.4f %.4f" % (e5,e10,e20,e30)
    return r


# ── STEP 5: CANDLE PATTERN ──────────────────────────────────────
def step5_candle(df, direction):
    r = {"score":0,"pattern":None,"detail":""}
    if df is None or len(df) < 3:
        return r
    o  = df["open"].iloc[-1];  c  = df["close"].iloc[-1]
    h  = df["high"].iloc[-1];  l  = df["low"].iloc[-1]
    o2 = df["open"].iloc[-2];  c2 = df["close"].iloc[-2]

    body  = abs(c - o)
    rng   = h - l
    if rng == 0:
        r["detail"] = "Doji"
        return r

    upper = h - max(o,c)
    lower = min(o,c) - l
    ratio = body / rng
    avg   = (df["close"]-df["open"]).abs().iloc[-10:].mean()

    if direction == "BUY":
        engulf = c2<o2 and c>o and c>o2 and o<c2 and body>avg*0.7
        pin    = lower>body*1.2 and lower>upper and ratio<0.5
        reject = c>o and ratio>0.4 and body>avg*0.7
    else:
        engulf = c2>o2 and c<o and c<o2 and o>c2 and body>avg*0.7
        pin    = upper>body*1.2 and upper>lower and ratio<0.5
        reject = c<o and ratio>0.4 and body>avg*0.7

    if engulf:
        r.update({"pattern":"ENGULFING","score":15,
                  "detail":"Engulfing candle %s" % direction})
    elif pin:
        r.update({"pattern":"PIN_BAR","score":15,
                  "detail":"Pin bar (ratio=%.2f)" % ratio})
    elif reject:
        r.update({"pattern":"REJECTION","score":15,
                  "detail":"Strong rejection (ratio=%.2f)" % ratio})
    else:
        r["detail"] = "No pattern (ratio=%.2f body=%.5f avg=%.5f)" % (ratio,body,avg)
    return r


# ── STEP 6: LEVELS ──────────────────────────────────────────────
def step6_levels(df, direction, pip):
    c    = df["close"]
    h    = df["high"]
    l    = df["low"]
    p    = c.iloc[-1]
    atr_v = atr(h, l, c).iloc[-1]
    sh   = h.iloc[-20:].max()
    sl_  = l.iloc[-20:].min()

    if direction == "BUY":
        entry = p
        sl    = round(sl_ - atr_v*0.5, 5)
        risk  = max(entry-sl, atr_v)
        tp1   = round(entry + risk*TP_RR_RATIO,     5)
        tp2   = round(entry + risk*TP_RR_RATIO*1.5, 5)
    else:
        entry = p
        sl    = round(sh  + atr_v*0.5, 5)
        risk  = max(sl-entry, atr_v)
        tp1   = round(entry - risk*TP_RR_RATIO,     5)
        tp2   = round(entry - risk*TP_RR_RATIO*1.5, 5)

    return {
        "entry":    round(entry,5),
        "sl":       round(sl,5),
        "tp1":      tp1,
        "tp2":      tp2,
        "risk_pips":round(risk/pip,1),
        "rr":       round(abs(tp1-entry)/risk,2),
    }


# ── STEP 7: SCORE ───────────────────────────────────────────────
def step7_score(s1,s2,s3,s4,s5):
    total = s1["score"]+s2["score"]+s3["score"]+s4["score"]+s5["score"]
    pct   = round(total/90*100,1)
    return {
        "HTF":s1["score"],"Setup":s2["score"],"SMC":s3["score"],
        "EMA":s4["score"],"Candle":s5["score"],
        "total":total,"max":90,"pct":pct,"passed":pct>=MIN_SCORE
    }


# ── TELEGRAM ────────────────────────────────────────────────────
def send_telegram(sig):
    smc   = sig["smc"]
    sc    = sig["score"]
    arrow = "BUY >>>" if sig["direction"]=="BUY" else "<<< SELL"
    smc_s = " | ".join(filter(None,[
        "LiqSweep" if smc["liq_sweep"]   else "",
        "OB"       if smc["order_block"] else "",
        "FVG"      if smc["fvg"]         else "",
    ])) or "---"

    msg = (
        "%s  *%s -- %s SIGNAL*\n"
        "--------------------------------\n\n"
        "Entry:   `%s`\n"
        "TP1:     `%s`\n"
        "TP2:     `%s`\n"
        "SL:      `%s`\n"
        "R:R:     1:%s\n"
        "Risk:    %s pips\n\n"
        "--------------------------------\n"
        "Score:   %s%%\n"
        "Setup:   %s\n"
        "Candle:  %s\n"
        "SMC:     %s\n\n"
        "HTF:%s/25 | Setup:%s/15 | SMC:%s/20 | EMA:%s/15 | Candle:%s/15\n\n"
        "Source: MT5 Real-Time\n"
        "Time: %s\n\n"
        "_Risk management -- max 1-2 pct per trade_"
    ) % (
        arrow, sig["pair"], sig["direction"],
        sig["entry"], sig["tp1"], sig["tp2"], sig["sl"],
        sig["lv"]["rr"], sig["lv"]["risk_pips"],
        sig["score"]["pct"],
        sig["setup"], sig["candle"], smc_s,
        sc["HTF"],sc["Setup"],sc["SMC"],sc["EMA"],sc["Candle"],
        sig["timestamp"]
    )

    url = "https://api.telegram.org/bot%s/sendMessage" % TELEGRAM_BOT_TOKEN
    try:
        r = requests.post(url, json={
            "chat_id":CHANNEL_ID,"text":msg,"parse_mode":"Markdown"
        }, timeout=10)
        if r.status_code == 200:
            logger.info("Telegram sent: %s %s score=%s%%",
                        sig["pair"], sig["direction"], sig["score"]["pct"])
        else:
            logger.error("Telegram error: %s", r.text[:200])
    except Exception as e:
        logger.error("Telegram failed: %s", e)


# ── MAIN ENGINE ─────────────────────────────────────────────────
class SignalProMT5:
    def __init__(self):
        self.mt5_mgr  = MT5Manager()
        self.last_sig = {}

    def start(self):
        return self.mt5_mgr.connect()

    def should_send(self, pair):
        last = self.last_sig.get(pair)
        if not last:
            return True
        return (datetime.now(timezone.utc)-last).seconds/60 >= SIGNAL_COOLDOWN

    def analyze(self, name, cfg):
        sym = cfg["symbol"]
        logger.info("  [%s] Fetching...", sym)

        df1h = self.mt5_mgr.get_candles(sym, cfg["htf1"], 100)
        df4h = self.mt5_mgr.get_candles(sym, cfg["htf2"], 80)
        dfl  = self.mt5_mgr.get_candles(sym, cfg["ltf"],  150)
        tick = self.mt5_mgr.get_tick(sym)

        if dfl is None:
            logger.info("  [%s] No LTF data", sym)
            return None

        if tick:
            logger.info("  [%s] Bid=%s Ask=%s Spread=%s",
                        sym, tick["bid"], tick["ask"], tick["spread"])

        s1 = step1_htf(df1h, df4h)
        if not s1["score"]:
            logger.info("  [%s] [NO] S1: %s", sym, s1["detail"])
            return None
        d = s1["direction"]
        logger.info("  [%s] [OK] S1: %s", sym, s1["detail"])

        s2 = step2_setup(dfl, d)
        if not s2["score"]:
            logger.info("  [%s] [NO] S2: %s", sym, s2["detail"])
            return None
        logger.info("  [%s] [OK] S2: %s", sym, s2["detail"])

        s3 = step3_smc(dfl, d)
        if not s3["score"]:
            logger.info("  [%s] [NO] S3: %s", sym, s3["detail"])
            return None
        logger.info("  [%s] [OK] S3: %s", sym, s3["detail"])

        s4 = step4_ema(dfl, d)
        if not s4["score"]:
            logger.info("  [%s] [NO] S4: %s", sym, s4["detail"])
            return None
        logger.info("  [%s] [OK] S4: %s", sym, s4["detail"])

        s5 = step5_candle(dfl, d)
        if not s5["score"]:
            logger.info("  [%s] [NO] S5: %s", sym, s5["detail"])
            return None
        logger.info("  [%s] [OK] S5: %s", sym, s5["detail"])

        lv = step6_levels(dfl, d, cfg["pip"])
        sc = step7_score(s1,s2,s3,s4,s5)
        logger.info("  [%s] Score: %s%% -- %s",
                    sym, sc["pct"], "PASS" if sc["passed"] else "FAIL")
        if not sc["passed"]:
            return None

        if tick:
            lv["entry"] = round(tick["ask"] if d=="BUY" else tick["bid"], 5)

        return {
            "pair":      name,
            "direction": d,
            "entry":     lv["entry"],
            "tp1":       lv["tp1"],
            "tp2":       lv["tp2"],
            "sl":        lv["sl"],
            "lv":        lv,
            "score":     sc,
            "setup":     s2.get("setup"),
            "candle":    s5.get("pattern"),
            "smc":       {"liq_sweep":s3["liq_sweep"],
                          "order_block":s3["order_block"],
                          "fvg":s3["fvg"]},
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        }

    def run_once(self):
        logger.info("=" * 50)
        logger.info("SCAN: %s | Min Score: %s%%",
                    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                    MIN_SCORE)
        if not self.mt5_mgr.check_connection():
            logger.error("MT5 reconnect failed")
            return []

        found = []
        for name, cfg in PAIRS.items():
            try:
                sig = self.analyze(name, cfg)
                if sig and self.should_send(name):
                    send_telegram(sig)
                    self.last_sig[name] = datetime.now(timezone.utc)
                    found.append(sig)
                    with open("signals_history.json","a") as f:
                        out = {k:v for k,v in sig.items() if k not in ["lv","score"]}
                        f.write(json.dumps(out)+"\n")
            except Exception as e:
                logger.error("%s error: %s", name, e)
            time.sleep(0.5)

        logger.info("Scan done -- Signals found: %s", len(found))
        return found

    def run_forever(self, interval_min=15):
        logger.info("SignalPro MT5 v3.1 Starting")
        logger.info("Pairs: %s", list(PAIRS.keys()))
        logger.info("Min Score: %s%% | Interval: %smin", MIN_SCORE, interval_min)
        if not self.start():
            logger.error("MT5 connect failed")
            return
        try:
            while True:
                try:
                    self.run_once()
                except Exception as e:
                    logger.error("Scan error: %s", e)
                logger.info("Next scan in %s min...", interval_min)
                time.sleep(interval_min * 60)
        except KeyboardInterrupt:
            logger.info("Stopped by user")
        finally:
            self.mt5_mgr.disconnect()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SignalPro MT5")
    parser.add_argument("--once",     action="store_true")
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument("--score",    type=int, default=MIN_SCORE)
    args = parser.parse_args()
    if args.score != MIN_SCORE:
        MIN_SCORE = args.score
    engine = SignalProMT5()
    if args.once:
        if engine.start():
            engine.run_once()
            engine.mt5_mgr.disconnect()
    else:
        engine.run_forever(interval_min=args.interval)
