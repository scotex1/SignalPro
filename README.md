# SignalPro FX — Complete Setup Guide
## Forex & Gold Signal System | Telegram + MT4 + Subscription

---

## 📁 Project Structure

```
signalpro/
├── backend/
│   └── signal_engine.py      ← Main signal generator (indicators, API)
├── telegram_bot/
│   └── bot.py                ← Telegram bot (subscription + signals)
├── mt4_ea/
│   ├── SignalPro_EA.mq4      ← MT4 Expert Advisor
│   └── mt4_bridge.py         ← Python → MT4 file bridge
├── run.py                    ← Master runner (sab ek saath)
├── requirements.txt          ← Python packages
└── README.md                 ← Yeh file
```

---

## ⚡ QUICK START — 5 Steps

### Step 1: API Keys Lo (Free)

**Twelve Data (Price Data):**
1. https://twelvedata.com par signup karo
2. Dashboard → API Key copy karo
3. Free plan: 800 calls/day (enough hai!)

**Telegram Bot:**
1. Telegram pe @BotFather open karo
2. `/newbot` command dalo
3. Naam do: "SignalPro FX"
4. Username do: "signalpro_fx_bot"
5. Token copy karo

**Telegram Channel:**
1. Free channel banao: @signalpro_free
2. Premium channel banao: @signalpro_vip
3. Bot ko channel admin banao

---

### Step 2: Config Set Karo

`backend/signal_engine.py` mein:
```python
TWELVE_DATA_API_KEY = "aapki_key_yahan"
TELEGRAM_BOT_TOKEN  = "bot_token_yahan"
CHANNEL_ID          = "@signalpro_vip"
```

`telegram_bot/bot.py` mein:
```python
BOT_TOKEN     = "bot_token_yahan"
ADMIN_USER_ID = 123456789  # Aapka Telegram ID (@userinfobot se pata karo)
PAYMENT_UPI   = "aapka@upi"
```

---

### Step 3: Install & Run

```bash
# Install
pip install -r requirements.txt

# Test karo (demo signal)
python run.py --test

# Telegram bot chalaao (alag terminal)
python telegram_bot/bot.py

# Signal engine chalaao
python run.py
```

---

### Step 4: MT4 Setup

1. `mt4_ea/SignalPro_EA.mq4` copy karo MT4 ke Experts folder mein
2. MT4 → Navigator → Expert Advisors → Refresh
3. XAU/USD M15 chart pe EA drag karo
4. Settings: AutoTrade=false, AlertsOnly=true (test ke liye)
5. `mt4_ea/mt4_bridge.py` mein MT4_FILES_PATH update karo

---

### Step 5: VPS Pe Deploy Karo (24/7)

**Recommended VPS: Contabo (₹400/month)**
```bash
# Ubuntu 22.04 VPS pe:
sudo apt update && sudo apt install python3 python3-pip -y
git clone your-repo / upload files
pip install -r requirements.txt

# Background mein chalao (screen)
screen -S signalpro
python run.py
# Ctrl+A, D = detach

# Ya systemd service (recommended)
sudo nano /etc/systemd/system/signalpro.service
```

**systemd service file:**
```ini
[Unit]
Description=SignalPro FX Signal Engine
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/signalpro
ExecStart=/usr/bin/python3 run.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable signalpro
sudo systemctl start signalpro
sudo systemctl status signalpro
```

---

## 💰 Monetization — Paisa Kaise Kamao

### Telegram Subscription Model:
| Plan | Price | Duration |
|------|-------|----------|
| Monthly VIP | ₹999 | 30 days |
| 3 Month VIP | ₹2,499 | 90 days |
| Yearly VIP | ₹7,999 | 365 days |

### Expected Income (estimate):
- 50 subscribers × ₹999 = ₹49,950/month
- 100 subscribers × ₹999 = ₹99,900/month

### Growth Tips:
1. YouTube channel banao — "Free Forex Education"
2. Instagram pe daily signals share karo (2 free signals)
3. Testimonials collect karo (screenshots)
4. Refer & Earn program add karo

---

## 📊 Signal Logic

```
BUY Signal conditions (score ≥ 55%):
  ✅ EMA 8 > EMA 21 > EMA 50 (trend bullish)     +30pts
  ✅ RSI < 60 (not overbought)                    +20pts
  ✅ MACD histogram rising                         +25pts
  ✅ Price in lower Bollinger Band half             +25pts

SELL Signal (mirror conditions)

TP = ATR × 2.0  (1:2 risk/reward)
SL = ATR × 1.0  (ATR-based, dynamic)
```

---

## 🤖 Telegram Bot Commands

| Command | Description |
|---------|-------------|
| /start | Main menu |
| /signals | Latest signals (free: 2/day) |
| /subscribe | VIP plans dekho |
| /pay UTR | Payment submit karo |
| /status | Meri subscription |
| /admin | Admin panel (sirf aap) |
| /approve ID | Payment approve karo |
| /broadcast msg | Sab premium users ko message |

---

## ⚠️ Important Notes

1. **Pehle demo account pe test karo** — real money se nahi
2. Signal 100% accurate nahi hote — trading mein risk hai
3. Customers ko disclaimer dikhao — "Trading involves risk"
4. Free API ke rate limits hain — production mein paid plan lo
5. MT4 AutoTrade cautiously use karo

---

## 🆘 Support

- Twelve Data docs: https://twelvedata.com/docs
- python-telegram-bot: https://python-telegram-bot.org
- MT4 MQL4 docs: https://docs.mql4.com
