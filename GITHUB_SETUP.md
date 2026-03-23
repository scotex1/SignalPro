# SignalPro FX — GitHub se Manage Karo
## Complete Guide: Ek push = Auto Deploy

---

## Kyun GitHub?

| Bina GitHub | GitHub ke saath |
|-------------|-----------------|
| VPS pe manually copy karo | `git push` karo — khud deploy ho jaega |
| API keys code mein likhna padta | GitHub Secrets mein safe rehti hain |
| Code kho sakta hai | Version history, rollback possible |
| Team nahi add kar sakte | Contributors add kar sakte ho |
| Manually restart karna padta | Auto restart on every push |

---

## Step 1: GitHub Repo Banao

```bash
# Apne PC pe (Git Bash / Terminal)

# 1. GitHub pe naya private repo banao:
#    github.com → New Repository
#    Name: signalpro
#    Visibility: PRIVATE (important!)
#    README: No (hum khud add karenge)

# 2. Local folder ko GitHub se connect karo
cd signalpro/          # pichla wala folder
git init
git add .
git commit -m "Initial SignalPro setup"
git branch -M main
git remote add origin https://github.com/AAPKA_USERNAME/signalpro.git
git push -u origin main
```

---

## Step 2: .gitignore Banao (Important!)

Yeh file zaroor banao — API keys GitHub pe nahi jaani chahiye!

```gitignore
# .gitignore — yeh files GitHub pe mat bhejo

# Config (API keys yahan hain)
config/settings.env
*.env
.env

# Database (user data)
*.db
*.sqlite

# Logs
*.log
logs/

# Python
__pycache__/
*.pyc
*.pyo
.Python
venv/
.venv/

# Signals history (large file ban sakti hai)
signals_history.json

# OS files
.DS_Store
Thumbs.db
```

---

## Step 3: GitHub Secrets Set Karo

GitHub pe: **Your Repo → Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Value | Kahan se milega |
|-------------|-------|-----------------|
| `VPS_HOST` | `123.45.67.89` | VPS provider ka IP |
| `VPS_USER` | `ubuntu` | VPS ka SSH user |
| `VPS_SSH_KEY` | `-----BEGIN...` | VPS setup script ke baad milega |
| `TWELVE_DATA_KEY` | `abc123...` | twelvedata.com account |
| `TELEGRAM_TOKEN` | `123456:ABC...` | BotFather se |
| `TELEGRAM_CHANNEL` | `@signalpro_vip` | Apna channel |
| `ADMIN_USER_ID` | `123456789` | @userinfobot se pata karo |
| `PAYMENT_UPI` | `name@upi` | Aapka UPI |

### Admin User ID kaise pata karo:
```
1. Telegram pe @userinfobot ko message karo
2. Woh aapka numeric ID batayega
3. Woh number ADMIN_USER_ID mein daalo
```

---

## Step 4: VPS Setup (Sirf Ek Baar)

```bash
# VPS pe SSH karo
ssh ubuntu@YOUR_VPS_IP

# Setup script chalao
curl -O https://raw.githubusercontent.com/AAPKA_USERNAME/signalpro/main/vps_setup.sh
bash vps_setup.sh AAPKA_USERNAME

# Script ke baad private key copy karo
# Woh key GitHub Secrets mein VPS_SSH_KEY ke naam se daalo
```

### Config fill karo VPS pe:
```bash
nano /home/ubuntu/signalpro/config/settings.env
# Apni real values daalo aur save karo (Ctrl+X, Y, Enter)
```

### Services start karo:
```bash
sudo systemctl start signalpro-engine
sudo systemctl start signalpro-bot

# Status check
sudo systemctl status signalpro-engine
sudo systemctl status signalpro-bot
```

---

## Step 5: Daily Workflow — Itna Hi Karna Hai!

```bash
# Koi bhi change karo (code, config, etc.)
git add .
git commit -m "Signal strength improve kiya"
git push origin main

# ✅ GitHub Actions automatically:
#    → Code test karega
#    → VPS pe deploy karega
#    → Services restart karega
#    → Aapko Telegram pe success/fail batayega
```

---

## Useful Commands

```bash
# Logs real-time dekho
tail -f /home/ubuntu/signalpro/logs/engine.log
tail -f /home/ubuntu/signalpro/logs/bot.log

# Services restart karo
sudo systemctl restart signalpro-engine
sudo systemctl restart signalpro-bot

# Status check
sudo systemctl status signalpro-engine
sudo systemctl status signalpro-bot

# Purana version pe wapas jao (rollback)
git log --oneline          # commits dekho
git revert HEAD            # last commit undo karo
git push origin main       # VPS pe auto deploy ho jaega

# New pair add karo (example)
# 1. signal_engine.py mein PAIRS dict mein add karo
# 2. git add . && git commit -m "USD/CAD pair add kiya" && git push
# 3. Done! VPS pe khud update ho jaega
```

---

## GitHub Actions Kab Chalega

| Event | Action |
|-------|--------|
| `main` branch pe push | Full deploy |
| Pull request | Sirf test (deploy nahi) |
| Manual trigger | GitHub → Actions → Run workflow |

---

## Recommended Folder Structure

```
signalpro/                     ← GitHub repo root
├── .github/
│   └── workflows/
│       └── deploy.yml         ← Auto deploy magic
├── backend/
│   └── signal_engine.py       ← Signal logic
├── telegram_bot/
│   └── bot.py                 ← Subscription bot
├── mt4_ea/
│   ├── SignalPro_EA.mq4       ← MT4 expert advisor
│   └── mt4_bridge.py
├── services/
│   └── README_services.txt    ← Systemd service files
├── config/
│   └── settings.env.example   ← Template (real file gitignore mein)
├── vps_setup.sh               ← VPS first-time setup
├── run.py                     ← Master runner
├── requirements.txt           ← Python packages
├── .gitignore                 ← API keys ko protect karo
└── README.md
```

---

## Security Checklist

- [x] Repo **Private** hai
- [x] `.env` files `.gitignore` mein hain
- [x] API keys sirf GitHub Secrets mein hain
- [x] VPS SSH key GitHub Secrets mein hai
- [x] Database file (`*.db`) gitignore mein hai
- [ ] Regular backups (optional: `rsync` se backup VPS)

---

## Troubleshooting

**Deploy fail ho raha hai?**
```bash
# GitHub → Repo → Actions tab → Failed run → Logs dekho
```

**Service start nahi ho raha?**
```bash
sudo journalctl -u signalpro-engine -n 50 --no-pager
# Error message dekho aur config check karo
```

**Telegram bot respond nahi kar raha?**
```bash
tail -f /home/ubuntu/signalpro/logs/bot.log
# Mostly BOT_TOKEN galat hota hai
```

**VPS_SSH_KEY error?**
```bash
# VPS pe yeh run karo:
cat ~/.ssh/signalpro_deploy
# Poori key (BEGIN se END tak) GitHub Secret mein daalo
```
