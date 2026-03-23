"""
SignalPro — MT4 Bridge
=======================
Yeh Python script MT4 EA ke saath communicate karta hai.
Signal generate hone pe ek text file likhta hai jo MT4 EA padhta hai.

Path: apne MT4 ke Files folder mein copy karo
Default MT4 Files: C:/Users/USERNAME/AppData/Roaming/MetaQuotes/Terminal/TERMINAL_ID/MQL4/Files/
"""

import os
import json
import time
import logging
from pathlib import Path

logger = logging.getLogger("MT4Bridge")

# ─────────────────────────────────────────────────────
# MT4 ke Files folder ka path — apna path yahan daalo
# ─────────────────────────────────────────────────────
MT4_FILES_PATH = r"C:\Users\YOUR_USERNAME\AppData\Roaming\MetaQuotes\Terminal\COMMON\Files"
SIGNAL_FILE    = "signalpro_signal.txt"
HISTORY_FILE   = "signalpro_history.txt"


class MT4Bridge:
    """MT4 EA ke saath file-based communication"""

    def __init__(self, mt4_path: str = MT4_FILES_PATH):
        self.path = Path(mt4_path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.signal_path  = self.path / SIGNAL_FILE
        self.history_path = self.path / HISTORY_FILE
        logger.info(f"MT4 Bridge ready. Files path: {self.path}")

    def send_signal(self, signal: dict) -> bool:
        """
        MT4 EA ko signal bhejo.
        Format: "DIRECTION,ENTRY,TP1,SL,STRENGTH"
        """
        try:
            content = ",".join([
                signal["direction"],
                str(signal["entry"]),
                str(signal["tp1"]),
                str(signal["sl"]),
                str(signal["strength"]),
                signal["timestamp"],
                signal["pair"],
            ])
            with open(self.signal_path, "w") as f:
                f.write(content)

            logger.info(f"MT4 signal file likha: {content}")
            self._append_history(signal)
            return True

        except Exception as e:
            logger.error(f"MT4 bridge error: {e}")
            return False

    def _append_history(self, signal: dict):
        """History file mein signal save karo"""
        try:
            with open(self.history_path, "a") as f:
                f.write(json.dumps(signal) + "\n")
        except:
            pass

    def clear_signal(self):
        """Signal file saaf karo (trade execute hone ke baad)"""
        try:
            with open(self.signal_path, "w") as f:
                f.write("NONE,0,0,0,0")
        except:
            pass

    def read_mt4_status(self) -> dict:
        """
        MT4 se trade status padhna.
        EA ek status file likhta hai — open positions, P&L etc.
        """
        status_path = self.path / "signalpro_status.txt"
        if not status_path.exists():
            return {"status": "no_data"}
        try:
            with open(status_path) as f:
                content = f.read().strip()
            # Format: "OPEN_TRADES:2,TOTAL_PROFIT:45.50,LAST_TRADE:BUY"
            parts = dict(item.split(":") for item in content.split(",") if ":" in item)
            return parts
        except:
            return {"status": "parse_error"}


# ─────────────────────────────────────────────────────
# MT4 Setup Guide — terminal mein print hoga
# ─────────────────────────────────────────────────────
MT4_SETUP_GUIDE = """
╔══════════════════════════════════════════════════════╗
║         MT4 Setup Guide — SignalPro FX               ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  STEP 1: EA Copy Karo                                ║
║  ─────────────────                                   ║
║  SignalPro_EA.mq4 ko copy karo:                      ║
║  MT4 → File → Open Data Folder                       ║
║  → MQL4 → Experts folder mein paste karo             ║
║                                                      ║
║  STEP 2: Compile Karo                                ║
║  ────────────────────                                ║
║  MT4 → Navigator → Expert Advisors                   ║
║  Right-click → Refresh                               ║
║  SignalPro_EA double-click → Compile (F7)            ║
║                                                      ║
║  STEP 3: Chart Pe Lagao                              ║
║  ──────────────────────                              ║
║  Chart open karo (XAU/USD M15 recommended)           ║
║  Navigator se EA drag karo chart pe                  ║
║  Settings:                                           ║
║    • AutoTrade = false (pehle test karo)             ║
║    • AlertsOnly = true                               ║
║    • MagicNumber = 12345                             ║
║    • Allow DLL imports: YES                          ║
║    • Allow external experts: YES                     ║
║                                                      ║
║  STEP 4: Files Path Set Karo                         ║
║  ──────────────────────────                          ║
║  MT4 → Tools → Options → Expert Advisors             ║
║  ✅ Allow automated trading                          ║
║  ✅ Allow DLL imports                                ║
║  ✅ Allow import of external experts                 ║
║                                                      ║
║  STEP 5: Python Bridge Path                          ║
║  ──────────────────────────                          ║
║  MT4 Files folder dhundho:                           ║
║  File → Open Data Folder → MQL4 → Files             ║
║  Is path ko MT4_FILES_PATH mein daalo                ║
║                                                      ║
║  STEP 6: Test Mode                                   ║
║  ──────────────────                                  ║
║  Pehle demo account pe test karo!                    ║
║  Signal aane pe alert aayega                         ║
║  Sab theek ho to AutoTrade = true karo               ║
║                                                      ║
║  ✅ Complete! Signals ab MT4 chart pe dikhenge       ║
╚══════════════════════════════════════════════════════╝
"""

if __name__ == "__main__":
    print(MT4_SETUP_GUIDE)

    # Test bridge
    bridge = MT4Bridge()
    test_signal = {
        "pair":      "XAU/USD",
        "direction": "BUY",
        "entry":     2318.50,
        "tp1":       2335.00,
        "tp2":       2350.00,
        "sl":        2305.00,
        "strength":  78,
        "timestamp": "2024-01-15 10:30 UTC",
    }
    success = bridge.send_signal(test_signal)
    print(f"Test signal sent: {success}")
    print(f"File location: {bridge.signal_path}")
