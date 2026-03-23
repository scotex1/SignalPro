# ═══════════════════════════════════════════════════════════════
# SignalPro FX — VPS Systemd Service Files
# ═══════════════════════════════════════════════════════════════
#
# Yeh do services banao VPS pe:
#   1. signalpro-engine  → Signal generator (har 15 min scan)
#   2. signalpro-bot     → Telegram subscription bot
#
# Install karne ka tarika:
#   sudo cp services/signalpro-engine.service /etc/systemd/system/
#   sudo cp services/signalpro-bot.service    /etc/systemd/system/
#   sudo systemctl daemon-reload
#   sudo systemctl enable signalpro-engine signalpro-bot
#   sudo systemctl start  signalpro-engine signalpro-bot
# ═══════════════════════════════════════════════════════════════

# ───────────────────────────────────────────────────────────────
# FILE 1: /etc/systemd/system/signalpro-engine.service
# ───────────────────────────────────────────────────────────────
# [Unit]
# Description=SignalPro FX — Signal Engine
# After=network-online.target
# Wants=network-online.target
#
# [Service]
# Type=simple
# User=ubuntu
# WorkingDirectory=/home/ubuntu/signalpro
# EnvironmentFile=/home/ubuntu/signalpro/config/settings.env
# ExecStart=/usr/bin/python3 run.py
# Restart=always
# RestartSec=30
# StandardOutput=journal
# StandardError=journal
# SyslogIdentifier=signalpro-engine
#
# [Install]
# WantedBy=multi-user.target


# ───────────────────────────────────────────────────────────────
# FILE 2: /etc/systemd/system/signalpro-bot.service
# ───────────────────────────────────────────────────────────────
# [Unit]
# Description=SignalPro FX — Telegram Bot
# After=network-online.target
# Wants=network-online.target
#
# [Service]
# Type=simple
# User=ubuntu
# WorkingDirectory=/home/ubuntu/signalpro
# EnvironmentFile=/home/ubuntu/signalpro/config/settings.env
# ExecStart=/usr/bin/python3 telegram_bot/bot.py
# Restart=always
# RestartSec=10
# StandardOutput=journal
# StandardError=journal
# SyslogIdentifier=signalpro-bot
#
# [Install]
# WantedBy=multi-user.target
