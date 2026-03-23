#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# SignalPro FX — VPS First Time Setup Script
# ═══════════════════════════════════════════════════════════════
# Usage: bash vps_setup.sh YOUR_GITHUB_USERNAME
#
# Kya karta hai:
#   1. System update
#   2. Python + pip install
#   3. GitHub se repo clone
#   4. Dependencies install
#   5. Systemd services create + enable
#   6. SSH key generate (GitHub Actions ke liye)
# ═══════════════════════════════════════════════════════════════

set -e   # Koi error aaye to ruk jao

GITHUB_USER=${1:-"YOUR_GITHUB_USERNAME"}
REPO_NAME="signalpro"
APP_DIR="/home/$(whoami)/signalpro"
SERVICE_USER=$(whoami)

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   SignalPro FX — VPS Setup Starting      ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Step 1: System update ──────────────────────────────────────
echo "[1/7] System update kar raha hoon..."
sudo apt-get update -qq
sudo apt-get install -y python3 python3-pip python3-venv git curl rsync

# ── Step 2: Python version check ──────────────────────────────
PYTHON_VER=$(python3 --version)
echo "      Python: $PYTHON_VER ✓"

# ── Step 3: App directory ─────────────────────────────────────
echo "[2/7] App folder bana raha hoon: $APP_DIR"
mkdir -p $APP_DIR
mkdir -p $APP_DIR/config
mkdir -p $APP_DIR/logs

# ── Step 4: Clone GitHub repo ─────────────────────────────────
echo "[3/7] GitHub se clone kar raha hoon..."
if [ -d "$APP_DIR/.git" ]; then
    echo "      Already cloned. git pull kar raha hoon..."
    cd $APP_DIR && git pull origin main
else
    git clone https://github.com/$GITHUB_USER/$REPO_NAME.git $APP_DIR
fi

# ── Step 5: Python packages ───────────────────────────────────
echo "[4/7] Python packages install kar raha hoon..."
cd $APP_DIR
pip3 install -r requirements.txt --quiet
echo "      Packages installed ✓"

# ── Step 6: Config file template ─────────────────────────────
echo "[5/7] Config template bana raha hoon..."
if [ ! -f "$APP_DIR/config/settings.env" ]; then
    cat > $APP_DIR/config/settings.env << 'EOF'
# SignalPro FX — Configuration
# Yahan apni real values daalo!

TWELVE_DATA_API_KEY=YOUR_KEY_HERE
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
TELEGRAM_CHANNEL=@your_channel
ADMIN_USER_ID=123456789
PAYMENT_UPI=yourname@upi
EOF
    echo "      config/settings.env banaya — apni values daalo!"
fi

# ── Step 7: Systemd services ──────────────────────────────────
echo "[6/7] Systemd services install kar raha hoon..."

# Signal Engine service
sudo tee /etc/systemd/system/signalpro-engine.service > /dev/null << EOF
[Unit]
Description=SignalPro FX — Signal Engine
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/config/settings.env
ExecStart=/usr/bin/python3 run.py
Restart=always
RestartSec=30
StandardOutput=append:$APP_DIR/logs/engine.log
StandardError=append:$APP_DIR/logs/engine.log
SyslogIdentifier=signalpro-engine

[Install]
WantedBy=multi-user.target
EOF

# Telegram Bot service
sudo tee /etc/systemd/system/signalpro-bot.service > /dev/null << EOF
[Unit]
Description=SignalPro FX — Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/config/settings.env
ExecStart=/usr/bin/python3 telegram_bot/bot.py
Restart=always
RestartSec=10
StandardOutput=append:$APP_DIR/logs/bot.log
StandardError=append:$APP_DIR/logs/bot.log
SyslogIdentifier=signalpro-bot

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable signalpro-engine signalpro-bot
echo "      Services installed ✓"

# ── Step 8: SSH key for GitHub Actions ───────────────────────
echo "[7/7] GitHub Actions ke liye SSH key bana raha hoon..."
if [ ! -f ~/.ssh/signalpro_deploy ]; then
    ssh-keygen -t ed25519 -f ~/.ssh/signalpro_deploy -N "" -C "signalpro-github-actions"
    cat ~/.ssh/signalpro_deploy.pub >> ~/.ssh/authorized_keys
    chmod 600 ~/.ssh/authorized_keys
fi

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                   SETUP COMPLETE!                        ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║                                                          ║"
echo "║  ABHI KARO (important):                                  ║"
echo "║                                                          ║"
echo "║  1. Config fill karo:                                    ║"
echo "║     nano $APP_DIR/config/settings.env"
echo "║                                                          ║"
echo "║  2. GitHub Secrets mein yeh private key daalo:           ║"
echo "║     (VPS_SSH_KEY secret mein paste karo)                 ║"
echo "║                                                          ║"
cat ~/.ssh/signalpro_deploy
echo "║                                                          ║"
echo "║  3. Services start karo (config fill karne ke baad):     ║"
echo "║     sudo systemctl start signalpro-engine                ║"
echo "║     sudo systemctl start signalpro-bot                   ║"
echo "║                                                          ║"
echo "║  4. Logs check karo:                                     ║"
echo "║     tail -f $APP_DIR/logs/engine.log                     ║"
echo "║     tail -f $APP_DIR/logs/bot.log                        ║"
echo "║                                                          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
