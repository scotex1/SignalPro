"""
SignalPro FX — Master Runner
==============================
Sab systems ek saath chalao:
  1. Signal Engine (price fetch + analyze)
  2. Telegram Bot (auto send)
  3. MT4 Bridge (file write)

Usage:
  python run.py            # Normal mode
  python run.py --test     # Test mode (demo signal)
  python run.py --once     # Ek baar scan karo
"""

import sys
import asyncio
import threading
import logging
import argparse
import time
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-12s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("signalpro_master.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Master")

# ─────────────────────────────────────────────────────
# IMPORTS — pehle pip install karo (requirements.txt dekho)
# ─────────────────────────────────────────────────────
try:
    from backend.signal_engine import SignalPro, PriceDataFetcher, SignalGenerator, PAIRS
    from mt4_ea.mt4_bridge import MT4Bridge
    import requests
except ImportError as e:
    logger.error(f"Import error: {e}")
    logger.error("Run: pip install -r requirements.txt")
    sys.exit(1)

# ─────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────
TWELVE_DATA_API_KEY = "YOUR_TWELVE_DATA_KEY"
TELEGRAM_BOT_TOKEN  = "YOUR_TELEGRAM_BOT_TOKEN"
CHANNEL_ID          = "@your_channel"
SCAN_INTERVAL_MIN   = 15
ENABLE_MT4_BRIDGE   = False    # Windows pe True karo


class MasterRunner:
    """Sab systems ka coordinator"""

    def __init__(self):
        self.signal_engine = SignalPro()
        self.mt4_bridge    = MT4Bridge() if ENABLE_MT4_BRIDGE else None
        self.running       = False

    def send_to_all(self, signal: dict):
        """Signal ko Telegram + MT4 dono ko bhejo"""
        # 1. Telegram
        self.signal_engine.send_telegram(signal)

        # 2. MT4 Bridge
        if self.mt4_bridge:
            self.mt4_bridge.send_signal(signal)
            logger.info(f"MT4 bridge: signal file updated")

        logger.info(f"Signal distributed: {signal['pair']} {signal['direction']}")

    def run_scan(self):
        """Ek complete scan cycle"""
        logger.info(f"{'═'*50}")
        logger.info(f"Scan: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

        found_signals = []
        for name, config in PAIRS.items():
            df = self.signal_engine.fetcher.get_candles(
                config["symbol"], config["interval"]
            )
            signal = self.signal_engine.generator.analyze(df, config)

            if signal and self.signal_engine.should_send_signal(name):
                logger.info(f"✅ Signal: {name} {signal['direction']} @ {signal['entry']}")
                self.send_to_all(signal)
                self.signal_engine.last_signal_time[name] = datetime.utcnow()
                found_signals.append(signal)
            else:
                logger.info(f"   No signal: {name}")
            time.sleep(1.5)

        logger.info(f"Scan done. Signals found: {len(found_signals)}")
        return found_signals

    def run_forever(self):
        """Production loop"""
        self.running = True
        logger.info("SignalPro Master Runner started!")
        logger.info(f"Pairs: {list(PAIRS.keys())}")
        logger.info(f"Scan every: {SCAN_INTERVAL_MIN} minutes")
        logger.info(f"MT4 Bridge: {'ON' if ENABLE_MT4_BRIDGE else 'OFF'}")

        while self.running:
            try:
                self.run_scan()
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Scan error: {e}")

            logger.info(f"Next scan in {SCAN_INTERVAL_MIN} min...")
            try:
                time.sleep(SCAN_INTERVAL_MIN * 60)
            except KeyboardInterrupt:
                break

        logger.info("SignalPro stopped.")


def run_demo():
    """Demo — test ke liye fake signal bhejo"""
    logger.info("DEMO MODE — Test signal bhej raha hoon...")
    demo_signal = {
        "pair":      "XAU/USD",
        "direction": "BUY",
        "entry":     2318.50,
        "tp1":       2335.00,
        "tp2":       2350.00,
        "sl":        2305.00,
        "strength":  78,
        "rsi":       48.5,
        "atr_pips":  18.2,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "interval":  "15min",
    }
    runner = MasterRunner()
    runner.send_to_all(demo_signal)
    logger.info("Demo done! Telegram check karo.")


def main():
    parser = argparse.ArgumentParser(description="SignalPro FX Master Runner")
    parser.add_argument("--test", action="store_true", help="Demo signal bhejo")
    parser.add_argument("--once", action="store_true", help="Ek baar scan karo")
    args = parser.parse_args()

    if args.test:
        run_demo()
    elif args.once:
        runner = MasterRunner()
        runner.run_scan()
    else:
        runner = MasterRunner()
        runner.run_forever()


if __name__ == "__main__":
    main()
