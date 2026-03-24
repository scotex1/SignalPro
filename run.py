"""
SignalPro FX — Master Runner
Railway.app ke liye updated — Environment Variables se config leta hai
"""

import sys
import os
import logging
import argparse
import time
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-12s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler()]   # Railway logs stdout se padhta hai
)
logger = logging.getLogger("Master")

# ─────────────────────────────────────────────────────
# CONFIG — Railway Environment Variables se aata hai
# Locally: os.environ mein set karo
# Railway pe: Dashboard → Variables mein daalo
# ─────────────────────────────────────────────────────
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "")
TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHANNEL_ID          = os.environ.get("TELEGRAM_CHANNEL", "")
SCAN_INTERVAL_MIN   = int(os.environ.get("SCAN_INTERVAL_MIN", "15"))

if not TWELVE_DATA_API_KEY:
    logger.error("TWELVE_DATA_API_KEY environment variable set nahi hai!")
    logger.error("Railway Dashboard → Variables mein daalo")

if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable set nahi hai!")

try:
    from backend.signal_engine import SignalPro, PAIRS
    import requests
except ImportError as e:
    logger.error(f"Import error: {e}")
    logger.error("requirements.txt check karo")
    sys.exit(1)


class MasterRunner:
    def __init__(self):
        self.signal_engine = SignalPro()
        self.running = False

    def run_scan(self):
        logger.info(f"{'═'*50}")
        logger.info(f"Scan: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

        found = []
        for name, config in PAIRS.items():
            df = self.signal_engine.fetcher.get_candles(
                config["symbol"], config["interval"]
            )
            signal = self.signal_engine.generator.analyze(df, config)

            if signal and self.signal_engine.should_send_signal(name):
                logger.info(f"SIGNAL: {name} {signal['direction']} @ {signal['entry']}")
                self.signal_engine.send_telegram(signal)
                self.signal_engine.last_signal_time[name] = datetime.utcnow()
                found.append(signal)
            else:
                logger.info(f"No signal: {name}")
            time.sleep(1.5)

        logger.info(f"Scan done. Signals: {len(found)}")
        return found

    def run_forever(self):
        self.running = True
        logger.info("SignalPro started on Railway!")
        logger.info(f"Pairs: {list(PAIRS.keys())}")
        logger.info(f"Scan interval: {SCAN_INTERVAL_MIN} min")

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


def run_demo():
    logger.info("DEMO MODE...")
    demo_signal = {
        "pair": "XAU/USD", "direction": "BUY",
        "entry": 2318.50, "tp1": 2335.00, "tp2": 2350.00,
        "sl": 2305.00, "strength": 78, "rsi": 48.5,
        "atr_pips": 18.2,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "interval": "15min",
    }
    runner = MasterRunner()
    runner.signal_engine.send_telegram(demo_signal)
    logger.info("Demo signal bheja!")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if args.test:
        run_demo()
    elif args.once:
        MasterRunner().run_scan()
    else:
        MasterRunner().run_forever()


if __name__ == "__main__":
    main()
