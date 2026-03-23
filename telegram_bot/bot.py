"""
SignalPro FX — Telegram Subscription Bot
==========================================
Commands:
  /start    — Welcome + plans dikhao
  /subscribe — Premium lena
  /status   — Meri subscription check karo
  /signals  — Latest signals dekho
  /help     — Help
  /admin    — Admin panel (sirf aapke liye)

Library: python-telegram-bot==20.x
Install: pip install python-telegram-bot aiosqlite
"""

import asyncio
import sqlite3
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SignalBot")

# ─────────────────────────────────
# CONFIG — apni values yahan daalo
# ─────────────────────────────────
BOT_TOKEN        = "YOUR_BOT_TOKEN_HERE"
ADMIN_USER_ID    = 123456789           # Aapka Telegram numeric user ID
PAYMENT_UPI      = "yourname@upi"      # Ya USDT wallet address
CHANNEL_FREE     = "@your_free_channel"
CHANNEL_PREMIUM  = "@your_vip_channel"

PLANS = {
    "monthly":  {"name": "Monthly VIP",  "price": 999,  "days": 30,  "emoji": "🥈"},
    "quarterly":{"name": "3 Month VIP",  "price": 2499, "days": 90,  "emoji": "🥇"},
    "yearly":   {"name": "Yearly VIP",   "price": 7999, "days": 365, "emoji": "💎"},
}
FREE_SIGNALS_PER_DAY = 2   # Free users ke liye daily limit


# ─────────────────────────────────
# DATABASE
# ─────────────────────────────────
class Database:
    def __init__(self, db_path="signalpro.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                plan        TEXT DEFAULT 'free',
                expires_at  TEXT,
                joined_at   TEXT DEFAULT CURRENT_TIMESTAMP,
                signals_today INTEGER DEFAULT 0,
                last_signal_date TEXT
            );
            CREATE TABLE IF NOT EXISTS payments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                plan        TEXT,
                amount      INTEGER,
                utr_number  TEXT,
                status      TEXT DEFAULT 'pending',
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS signals_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                pair       TEXT,
                direction  TEXT,
                entry      REAL,
                tp1        REAL,
                tp2        REAL,
                sl         REAL,
                strength   INTEGER,
                sent_at    TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self.conn.commit()

    def get_user(self, user_id: int):
        cur = self.conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        if row:
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))
        return None

    def upsert_user(self, user_id, username, first_name):
        self.conn.execute("""
            INSERT INTO users (user_id, username, first_name) VALUES (?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name
        """, (user_id, username, first_name))
        self.conn.commit()

    def is_premium(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        if not user or user["plan"] == "free":
            return False
        if user["expires_at"]:
            exp = datetime.fromisoformat(user["expires_at"])
            return exp > datetime.utcnow()
        return False

    def activate_premium(self, user_id: int, plan_key: str):
        plan = PLANS[plan_key]
        expires = (datetime.utcnow() + timedelta(days=plan["days"])).isoformat()
        self.conn.execute(
            "UPDATE users SET plan=?, expires_at=? WHERE user_id=?",
            (plan_key, expires, user_id)
        )
        self.conn.commit()

    def save_payment(self, user_id, plan, amount, utr):
        self.conn.execute(
            "INSERT INTO payments (user_id, plan, amount, utr_number) VALUES (?,?,?,?)",
            (user_id, plan, amount, utr)
        )
        self.conn.commit()

    def approve_payment(self, payment_id: int):
        cur = self.conn.execute("SELECT * FROM payments WHERE id=?", (payment_id,))
        row = cur.fetchone()
        if row:
            cols = [d[0] for d in cur.description]
            p = dict(zip(cols, row))
            self.activate_premium(p["user_id"], p["plan"])
            self.conn.execute("UPDATE payments SET status='approved' WHERE id=?", (payment_id,))
            self.conn.commit()
            return p
        return None

    def get_pending_payments(self):
        cur = self.conn.execute("SELECT * FROM payments WHERE status='pending' ORDER BY created_at DESC")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def get_stats(self):
        total    = self.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        premium  = self.conn.execute("SELECT COUNT(*) FROM users WHERE plan!='free'").fetchone()[0]
        pending  = self.conn.execute("SELECT COUNT(*) FROM payments WHERE status='pending'").fetchone()[0]
        revenue  = self.conn.execute("SELECT SUM(amount) FROM payments WHERE status='approved'").fetchone()[0] or 0
        return {"total": total, "premium": premium, "pending": pending, "revenue": revenue}

    def can_see_signal(self, user_id: int) -> bool:
        if self.is_premium(user_id):
            return True
        user = self.get_user(user_id)
        if not user:
            return False
        today = datetime.utcnow().date().isoformat()
        if user["last_signal_date"] != today:
            self.conn.execute(
                "UPDATE users SET signals_today=0, last_signal_date=? WHERE user_id=?",
                (today, user_id)
            )
            self.conn.commit()
            user["signals_today"] = 0
        return user["signals_today"] < FREE_SIGNALS_PER_DAY

    def increment_signal_count(self, user_id):
        today = datetime.utcnow().date().isoformat()
        self.conn.execute(
            "UPDATE users SET signals_today=signals_today+1, last_signal_date=? WHERE user_id=?",
            (today, user_id)
        )
        self.conn.commit()


db = Database()


# ─────────────────────────────────
# HELPERS
# ─────────────────────────────────
def get_latest_signals():
    """signals_history.json se read karo ya demo data"""
    import json, os
    signals = []
    path = "../backend/signals_history.json"
    if os.path.exists(path):
        with open(path) as f:
            lines = f.readlines()[-5:]
            for line in lines:
                try:
                    signals.append(json.loads(line.strip()))
                except:
                    pass
    if not signals:
        # Demo signals jab file nahi ho
        signals = [
            {"pair":"XAU/USD","direction":"BUY","entry":2318.50,"tp1":2335.00,"tp2":2350.00,"sl":2305.00,"strength":78,"timestamp":"2024-01-15 10:30 UTC"},
            {"pair":"EUR/USD","direction":"SELL","entry":1.0842,"tp1":1.0810,"tp2":1.0785,"sl":1.0875,"strength":65,"timestamp":"2024-01-15 09:15 UTC"},
        ]
    return signals


# ─────────────────────────────────
# COMMAND HANDLERS
# ─────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name)

    is_vip = db.is_premium(user.id)
    status = "💎 VIP Member" if is_vip else "🆓 Free User"

    text = (
        f"🚀 *SignalPro FX mein aapka swagat hai!*\n\n"
        f"Namaste *{user.first_name}*! Aap currently *{status}* hain.\n\n"
        f"📊 Hum Forex aur Gold ke premium signals dete hain:\n"
        f"• XAU/USD (Gold)\n• EUR/USD\n• GBP/USD\n• USD/JPY\n\n"
        f"🆓 *Free Plan:* {FREE_SIGNALS_PER_DAY} signals/day\n"
        f"💎 *VIP Plan:* Unlimited signals + early access\n\n"
        f"Neeche se choose karo:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Latest Signals", callback_data="signals"),
         InlineKeyboardButton("💎 VIP Plans", callback_data="plans")],
        [InlineKeyboardButton("📈 Meri Status", callback_data="status"),
         InlineKeyboardButton("❓ Help", callback_data="help")],
    ])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def cmd_signals(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name)

    if not db.can_see_signal(user.id):
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("💎 VIP Lo — Unlimited Signals", callback_data="plans")
        ]])
        await update.message.reply_text(
            "⛔ Aapki aaj ki free limit khatam ho gayi!\n\n"
            f"Free plan: sirf *{FREE_SIGNALS_PER_DAY} signals/day*\n\n"
            "VIP lo aur unlimited signals pao! 👇",
            parse_mode="Markdown", reply_markup=kb
        )
        return

    signals = get_latest_signals()
    msg = "📊 *Latest Signals*\n" + "─"*30 + "\n\n"
    for s in signals[:3]:
        arrow = "🟢" if s["direction"] == "BUY" else "🔴"
        msg += (
            f"{arrow} *{s['pair']} — {s['direction']}*\n"
            f"📍 Entry: `{s['entry']}`\n"
            f"✅ TP1: `{s['tp1']}` | TP2: `{s['tp2']}`\n"
            f"❌ SL: `{s['sl']}`\n"
            f"💪 Strength: {s['strength']}%\n"
            f"⏰ {s['timestamp']}\n\n"
        )

    db.increment_signal_count(user.id)
    if not db.is_premium(user.id):
        u = db.get_user(user.id)
        remaining = max(0, FREE_SIGNALS_PER_DAY - u["signals_today"])
        msg += f"_Remaining free signals today: {remaining}_\n"

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("💎 VIP Lo — Unlimited", callback_data="plans")
    ]])
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)


async def cmd_subscribe(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await show_plans(update.message, update.effective_user)


async def show_plans(message, user):
    text = "💎 *VIP Plans — SignalPro FX*\n\n"
    for key, plan in PLANS.items():
        text += f"{plan['emoji']} *{plan['name']}*\n₹{plan['price']}/- | {plan['days']} days\n\n"
    text += "Plan chunne ke baad payment karo aur UTR send karo.\n✅ 30 min mein activate ho jaega!"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{p['emoji']} {p['name']} — ₹{p['price']}", callback_data=f"buy_{k}")]
        for k, p in PLANS.items()
    ] + [[InlineKeyboardButton("🔙 Back", callback_data="start")]])
    await message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = db.get_user(user.id)
    if not u:
        await update.message.reply_text("Pehle /start karo!")
        return

    if db.is_premium(user.id):
        exp = datetime.fromisoformat(u["expires_at"])
        days_left = (exp - datetime.utcnow()).days
        status_text = (
            f"💎 *VIP Member*\n\n"
            f"Plan: *{u['plan'].title()}*\n"
            f"Expires: {exp.strftime('%d %b %Y')}\n"
            f"Days remaining: *{days_left}*\n\n"
            f"✅ Unlimited signals active!"
        )
    else:
        today = datetime.utcnow().date().isoformat()
        signals_used = u["signals_today"] if u["last_signal_date"] == today else 0
        remaining = max(0, FREE_SIGNALS_PER_DAY - signals_used)
        status_text = (
            f"🆓 *Free User*\n\n"
            f"Signals used today: {signals_used}/{FREE_SIGNALS_PER_DAY}\n"
            f"Remaining: *{remaining}*\n\n"
            f"_VIP lo aur unlimited pao!_"
        )

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("💎 Upgrade to VIP", callback_data="plans")
    ]])
    await update.message.reply_text(status_text, parse_mode="Markdown", reply_markup=kb)


# ─────────────────────────────────
# CALLBACK QUERIES
# ─────────────────────────────────
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "plans":
        await show_plans(q.message, q.from_user)
    elif data == "signals":
        # Signals dikhao
        fake_update = type('obj', (object,), {'message': q.message, 'effective_user': q.from_user})()
        await cmd_signals(fake_update, ctx)
    elif data == "status":
        fake_update = type('obj', (object,), {'message': q.message, 'effective_user': q.from_user})()
        await cmd_status(fake_update, ctx)
    elif data.startswith("buy_"):
        plan_key = data[4:]
        plan = PLANS[plan_key]
        text = (
            f"{plan['emoji']} *{plan['name']}* — ₹{plan['price']}\n\n"
            f"💳 *Payment karo:*\n"
            f"UPI ID: `{PAYMENT_UPI}`\n"
            f"Amount: `₹{plan['price']}`\n\n"
            f"Payment ke baad /pay UTR_NUMBER bhejo\n"
            f"Example: `/pay 123456789012`\n\n"
            f"✅ 30 minute mein manually activate kar denge!"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Plans", callback_data="plans")]])
        await q.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    elif data == "help":
        await q.message.reply_text(
            "📖 *Commands:*\n\n"
            "/start — Main menu\n"
            "/signals — Latest signals dekho\n"
            "/subscribe — VIP plans\n"
            "/status — Aapki subscription\n"
            "/pay UTR — Payment submit karo\n\n"
            "Support: @your_support_username",
            parse_mode="Markdown"
        )


# ─────────────────────────────────
# PAYMENT SUBMISSION
# ─────────────────────────────────
async def cmd_pay(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = ctx.args

    if not args:
        await update.message.reply_text(
            "⚠️ UTR number bhejo:\n`/pay YOUR_UTR_NUMBER`",
            parse_mode="Markdown"
        )
        return

    utr = args[0]
    # Pending payment dhundho
    pending = db.get_pending_payments()
    user_pending = [p for p in pending if p["user_id"] == user.id]

    if not user_pending:
        await update.message.reply_text(
            "⚠️ Pehle plan select karo!\n/subscribe se plan chuno."
        )
        return

    latest = user_pending[-1]
    db.conn.execute(
        "UPDATE payments SET utr_number=? WHERE id=?",
        (utr, latest["id"])
    )
    db.conn.commit()

    # Admin ko notify karo
    admin_msg = (
        f"💰 *New Payment Received!*\n\n"
        f"User: {user.first_name} (@{user.username})\n"
        f"User ID: `{user.id}`\n"
        f"Plan: {latest['plan']}\n"
        f"Amount: ₹{latest['amount']}\n"
        f"UTR: `{utr}`\n\n"
        f"Approve karne ke liye:\n`/approve {latest['id']}`"
    )
    try:
        await ctx.bot.send_message(ADMIN_USER_ID, admin_msg, parse_mode="Markdown")
    except:
        pass

    await update.message.reply_text(
        f"✅ *Payment receive hua!*\n\n"
        f"UTR: `{utr}`\n"
        f"Plan: {latest['plan']}\n\n"
        f"30 minute mein activate ho jaega!\n"
        f"Koi problem ho to: @your_support_username",
        parse_mode="Markdown"
    )


# ─────────────────────────────────
# ADMIN COMMANDS
# ─────────────────────────────────
async def cmd_approve(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return

    if not ctx.args:
        await update.message.reply_text("Usage: /approve PAYMENT_ID")
        return

    payment_id = int(ctx.args[0])
    payment = db.approve_payment(payment_id)

    if payment:
        plan = PLANS.get(payment["plan"], {})
        # User ko notify karo
        try:
            await ctx.bot.send_message(
                payment["user_id"],
                f"🎉 *Aapka VIP Activate Ho Gaya!*\n\n"
                f"Plan: {plan.get('name','VIP')}\n"
                f"✅ Ab unlimited signals milenge!\n\n"
                f"Channel join karo: {CHANNEL_PREMIUM}",
                parse_mode="Markdown"
            )
        except:
            pass
        await update.message.reply_text(f"✅ Payment {payment_id} approved!")
    else:
        await update.message.reply_text("Payment not found.")


async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return

    stats = db.get_stats()
    pending = db.get_pending_payments()

    text = (
        f"📊 *Admin Panel*\n\n"
        f"👥 Total users: {stats['total']}\n"
        f"💎 Premium users: {stats['premium']}\n"
        f"💰 Total revenue: ₹{stats['revenue']}\n"
        f"⏳ Pending payments: {stats['pending']}\n\n"
    )
    if pending:
        text += "*Pending Payments:*\n"
        for p in pending[:5]:
            text += f"ID:{p['id']} | User:{p['user_id']} | ₹{p['amount']} | UTR:{p['utr_number']}\n"
            text += f"Approve: `/approve {p['id']}`\n\n"

    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Premium users ko broadcast"""
    if update.effective_user.id != ADMIN_USER_ID:
        return
    if not ctx.args:
        await update.message.reply_text("Usage: /broadcast Your message here")
        return

  msg = " ".join(ctx.args)
    cur = db.conn.execute("SELECT user_id FROM users WHERE plan != 'free'")
    users = cur.fetchall()
    sent = 0
    for (uid,) in users:
        try:
            await ctx.bot.send_message(uid, f"📢 *Announcement*\n\n{msg}", parse_mode="Markdown")
            sent += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await update.message.reply_text(f"✅ Sent to {sent} premium users")


# ─────────────────────────────────
# MAIN
# ─────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("signals",    cmd_signals))
    app.add_handler(CommandHandler("subscribe",  cmd_subscribe))
    app.add_handler(CommandHandler("status",     cmd_status))
    app.add_handler(CommandHandler("pay",        cmd_pay))
    app.add_handler(CommandHandler("admin",      cmd_admin))
    app.add_handler(CommandHandler("approve",    cmd_approve))
    app.add_handler(CommandHandler("broadcast",  cmd_broadcast))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("SignalPro Telegram Bot started!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
