"""
SignalPro FX - Main Signal Engine
==================================
Forex & Gold ke liye automatic BUY/SELL signals
Price data: Twelve Data (Free API)
Indicators: EMA, RSI, MACD, Bollinger Bands
"""

import requests
import pandas as pd
import numpy as np
import time
import json
import logging
from datetime import datetime
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler("signalpro.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("SignalPro")

# ─────────────────────────────────────────
# CONFIGURATION — apni values yahan daalo
# ─────────────────────────────────────────
TWELVE_DATA_API_KEY = "YOUR_TWELVE_DATA_API_KEY"   # https://twelvedata.com se free key lo
TELEGRAM_BOT_TOKEN  = "YOUR_TELEGRAM_BOT_TOKEN"     # BotFather se banao
CHANNEL_ID          = "@your_channel_name"           # ya numeric id: -1001234567890

PAIRS = {
    "XAU/USD": {"symbol": "XAU/USD", "interval": "15min", "pip_value": 0.1},
    "EUR/USD": {"symbol": "EUR/USD", "interval": "15min", "pip_value": 0.0001},
    "GBP/USD": {"symbol": "GBP/USD", "interval": "15min", "pip_value": 0.0001},
    "USD/JPY": {"symbol": "USD/JPY", "interval": "15min", "pip_value": 0.01},
}

# Risk/Reward settings
TP_MULTIPLIER = 2.0   # 1:2 risk/reward
SL_MULTIPLIER = 1.0   # ATR based stop loss
ATR_PERIOD    = 14
SIGNAL_COOLDOWN_MINUTES = 60   # ek pair pe baar baar signal nahi


class PriceDataFetcher:
    """Twelve Data API se OHLCV data fetch karta hai"""

    BASE_URL = "https://api.twelvedata.com"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()

    def get_candles(self, symbol: str, interval: str = "15min", outputsize: int = 100) -> Optional[pd.DataFrame]:
        """OHLCV candle data fetch karo"""
        url = f"{self.BASE_URL}/time_series"
        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": self.api_key,
            "format": "JSON",
        }
        try:
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()

            if "values" not in data:
                logger.warning(f"No data for {symbol}: {data.get('message','unknown error')}")
                return None

            df = pd.DataFrame(data["values"])
            df["datetime"] = pd.to_datetime(df["datetime"])
            df = df.sort_values("datetime").reset_index(drop=True)
            for col in ["open","high","low","close","volume"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df

        except Exception as e:
            logger.error(f"API error for {symbol}: {e}")
            return None

    def get_current_price(self, symbol: str) -> Optional[float]:
        url = f"{self.BASE_URL}/price"
        params = {"symbol": symbol, "apikey": self.api_key}
        try:
            resp = self.session.get(url, params=params, timeout=5)
            data = resp.json()
            return float(data.get("price", 0)) or None
        except:
            return None


class TechnicalIndicators:
    """Sab indicators calculate karna"""

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain  = delta.clip(lower=0)
        loss  = -delta.clip(upper=0)
        avg_g = gain.ewm(com=period-1, adjust=False).mean()
        avg_l = loss.ewm(com=period-1, adjust=False).mean()
        rs    = avg_g / avg_l
        return 100 - (100 / (1 + rs))

    @staticmethod
    def macd(series: pd.Series, fast=12, slow=26, signal=9):
        ema_fast   = series.ewm(span=fast, adjust=False).mean()
        ema_slow   = series.ewm(span=slow, adjust=False).mean()
        macd_line  = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram  = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def bollinger_bands(series: pd.Series, period=20, std_dev=2):
        mid   = series.rolling(period).mean()
        std   = series.rolling(period).std()
        upper = mid + (std * std_dev)
        lower = mid - (std * std_dev)
        return upper, mid, lower

    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, period=14) -> pd.Series:
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs()
        ], axis=1).max(axis=1)
        return tr.ewm(span=period, adjust=False).mean()


class SignalGenerator:
    """
    Signal logic:
    BUY  → EMA crossover + RSI < 60 + MACD bullish + price near lower BB
    SELL → EMA crossover + RSI > 40 + MACD bearish + price near upper BB
    """

    def __init__(self):
        self.ind = TechnicalIndicators()

    def analyze(self, df: pd.DataFrame, pair_config: dict) -> Optional[dict]:
        if df is None or len(df) < 50:
            return None

        close = df["close"]
        high  = df["high"]
        low   = df["low"]

        # Calculate indicators
        ema8   = self.ind.ema(close, 8)
        ema21  = self.ind.ema(close, 21)
        ema50  = self.ind.ema(close, 50)
        rsi    = self.ind.rsi(close)
        macd, macd_sig, macd_hist = self.ind.macd(close)
        bb_up, bb_mid, bb_low = self.ind.bollinger_bands(close)
        atr    = self.ind.atr(high, low, close, ATR_PERIOD)

        # Latest values
        i = -1
        p  = close.iloc[i]
        e8 = ema8.iloc[i]; e21 = ema21.iloc[i]; e50 = ema50.iloc[i]
        r  = rsi.iloc[i]
        mh = macd_hist.iloc[i]; mh_prev = macd_hist.iloc[-2]
        bb_u = bb_up.iloc[i]; bb_l = bb_low.iloc[i]; bb_m = bb_mid.iloc[i]
        atr_v = atr.iloc[i]

        # Scoring system (0-100)
        score = 0
        direction = None

        # BUY conditions
        buy_score = 0
        if e8 > e21 > e50:            buy_score += 30  # EMA trend bullish
        if r < 60:                     buy_score += 20  # RSI not overbought
        if mh > 0 and mh > mh_prev:   buy_score += 25  # MACD histogram rising
        if p < bb_m + (bb_u - bb_m)*0.3: buy_score += 25  # price in lower half of BB

        # SELL conditions
        sell_score = 0
        if e8 < e21 < e50:             sell_score += 30
        if r > 40:                      sell_score += 20
        if mh < 0 and mh < mh_prev:    sell_score += 25
        if p > bb_m - (bb_m - bb_l)*0.3: sell_score += 25

        if buy_score > sell_score and buy_score >= 55:
            direction = "BUY"
            score = buy_score
        elif sell_score > buy_score and sell_score >= 55:
            direction = "SELL"
            score = sell_score
        else:
            return None   # signal nahi — market unclear

        # TP / SL calculate karo
        pip = pair_config["pip_value"]
        atr_pips = atr_v / pip

        if direction == "BUY":
            sl  = round(p - atr_v * SL_MULTIPLIER, 5)
            tp1 = round(p + atr_v * TP_MULTIPLIER, 5)
            tp2 = round(p + atr_v * TP_MULTIPLIER * 1.5, 5)
        else:
            sl  = round(p + atr_v * SL_MULTIPLIER, 5)
            tp1 = round(p - atr_v * TP_MULTIPLIER, 5)
            tp2 = round(p - atr_v * TP_MULTIPLIER * 1.5, 5)

        return {
            "pair":      pair_config["symbol"],
            "direction": direction,
            "entry":     round(p, 5),
            "tp1":       tp1,
            "tp2":       tp2,
            "sl":        sl,
            "strength":  score,
            "rsi":       round(r, 1),
            "atr_pips":  round(atr_pips, 1),
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "interval":  pair_config["interval"],
        }


class SignalPro:
    """Main orchestrator — sab cheez ek jagah"""

    def __init__(self):
        self.fetcher   = PriceDataFetcher(TWELVE_DATA_API_KEY)
        self.generator = SignalGenerator()
        self.last_signal_time = {}   # cooldown tracking

    def should_send_signal(self, pair: str) -> bool:
        last = self.last_signal_time.get(pair)
        if last is None:
            return True
        elapsed = (datetime.utcnow() - last).total_seconds() / 60
        return elapsed >= SIGNAL_COOLDOWN_MINUTES

    def send_telegram(self, signal: dict):
        arrow = "🟢" if signal["direction"] == "BUY" else "🔴"
        msg = (
            f"{arrow} *{signal['pair']} — {signal['direction']} SIGNAL*\n\n"
            f"📍 *Entry:*  `{signal['entry']}`\n"
            f"✅ *TP1:*    `{signal['tp1']}`\n"
            f"✅ *TP2:*    `{signal['tp2']}`\n"
            f"❌ *SL:*     `{signal['sl']}`\n\n"
            f"📊 *RSI:* {signal['rsi']} | *ATR:* {signal['atr_pips']} pips\n"
            f"💪 *Strength:* {signal['strength']}%\n"
            f"⏰ *Time:* {signal['timestamp']}\n"
            f"📈 *TF:* {signal['interval']}\n\n"
            f"⚠️ _Risk management zaroor karo. 1-2% per trade._"
        )
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHANNEL_ID,
            "text": msg,
            "parse_mode": "Markdown"
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info(f"Telegram pe signal bheja: {signal['pair']} {signal['direction']}")
            else:
                logger.error(f"Telegram error: {resp.text}")
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    def run_once(self):
        """Ek scan — sab pairs check karo"""
        logger.info("─" * 50)
        logger.info(f"Scan start: {datetime.utcnow().strftime('%H:%M:%S UTC')}")

        for name, config in PAIRS.items():
            logger.info(f"Checking {name}...")
            df = self.fetcher.get_candles(config["symbol"], config["interval"])
            signal = self.generator.analyze(df, config)

            if signal and self.should_send_signal(name):
                logger.info(f"SIGNAL FOUND: {name} {signal['direction']} @ {signal['entry']}")
                self.send_telegram(signal)
                self.last_signal_time[name] = datetime.utcnow()

                # Save to local log file
                with open("signals_history.json", "a") as f:
                    f.write(json.dumps(signal) + "\n")
            else:
                logger.info(f"No signal for {name}")

            time.sleep(1.5)   # API rate limit respect karo

    def run_forever(self, scan_interval_minutes: int = 15):
        """Continuous loop — production mein yahi chalao"""
        logger.info("SignalPro FX started!")
        logger.info(f"Pairs: {list(PAIRS.keys())}")
        logger.info(f"Scan interval: {scan_interval_minutes} min")

        while True:
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"Scan error: {e}")

            logger.info(f"Next scan in {scan_interval_minutes} minutes...")
            time.sleep(scan_interval_minutes * 60)


if __name__ == "__main__":
    bot = SignalPro()
    bot.run_forever(scan_interval_minutes=15)
