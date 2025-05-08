import os
import re
import json
import logging
import asyncio
from pathlib import Path
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from db import create_db, save_to_db, calculate_daily_summary, clear_db
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.constants import ParseMode
from utils import parse_pnl_message
from datetime import datetime, timedelta
import pytz

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
YOUR_CHAT_ID = int(os.getenv("YOUR_CHAT_ID"))
scheduler = AsyncIOScheduler()
SETTINGS_FILE = "settings.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {}
    with open(SETTINGS_FILE, "r") as f:
        return json.load(f)

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)

def schedule_daily_summary(hour: int, minute: int, bot, chat_id):
    settings = load_settings()
    timezone_name = settings.get("timezone_name", "UTC")

    try:
        user_tz = pytz.timezone(timezone_name)
    except Exception as e:
        logging.error(f"Invalid timezone in settings: {timezone_name}")
        user_tz = pytz.utc

    now_local = datetime.now(user_tz)
    target_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target_local <= now_local:
        target_local += timedelta(days=1)

    target_utc = target_local.astimezone(pytz.utc)

    for job in scheduler.get_jobs():
        job.remove()

    trigger = CronTrigger(hour=target_utc.hour, minute=target_utc.minute, timezone=pytz.utc)

    scheduler.add_job(
        send_daily_summary,
        trigger=trigger,
        kwargs={"bot": bot, "chat_id": chat_id}
    )

    logging.info(f"📅 Daily summary scheduled for {target_utc.strftime('%Y-%m-%d %H:%M')} UTC")
    logging.info(f"⏰ Local time set by user: {hour:02d}:{minute:02d} ({timezone_name})")

async def send_daily_summary(bot, chat_id):
    summary = calculate_daily_summary()
    if not summary:
        logging.info(f"No data to send for chat {chat_id}")
        return

    msg = "📊 Daily Summary:\n"
    for currency, data in summary.items():
        msg += (
            f"\n💰 *{currency}*\n"
            f"🟢 Profit: `{data['profit']:.4f}`\n"
            f"🔴 Loss: `{data['loss']:.4f}`\n"
            f"📈 Net: `{data['net']:.4f}`\n"
        )

    await bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.MARKDOWN)
    clear_db()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I am a Profit Pulse Bot for tracking profit 💰")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    if "Realized PNL" in msg:
        parsed = parse_pnl_message(msg)
        if parsed:
            pair, amount, currency = parsed
            save_to_db(pair, amount, currency)
            await update.message.reply_text(f"Saved: {pair} {amount}{currency}")
        else:
            await update.message.reply_text("⚠️ Message format not recognized.")

async def manual_calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    summary = calculate_daily_summary()

    if not summary:
        await update.message.reply_text("📭 You have no realized PNL orders for today.")
        return

    msg = "📊 Manual Summary by Currency:\n"

    for currency, data in summary.items():
        msg += (
            f"\n💰 *{currency}*\n"
            f"🟢 Profit: `{data['profit']:.4f}`\n"
            f"🔴 Loss: `{data['loss']:.4f}`\n"
            f"📈 Net: `{data['net']:.4f}`\n"
        )

    await update.message.reply_text(msg, parse_mode='Markdown')

async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    bot = context.bot

    settings = load_settings()
    if "timezone_name" not in settings:
        await update.message.reply_text("🌍 Please set your timezone first using /set_timezone Europe/Kyiv")
        return

    if not context.args or not re.match(r"^\d{1,2}:\d{2}$", context.args[0]):
        await update.message.reply_text("⚠️ Use format: /set_time HH:MM (24h format)")
        return

    time_str = context.args[0]
    hour, minute = map(int, time_str.split(":"))

    if not (0 <= hour < 24 and 0 <= minute < 60):
        await update.message.reply_text("⛔️ Invalid time. Use HH:MM in 24h format.")
        return

    schedule_daily_summary(hour, minute, bot, chat_id)
    await update.message.reply_text(f"✅ Daily summary time set to {hour:02d}:{minute:02d} (your local time)")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for job in scheduler.get_jobs():
        job.remove()
    clear_db()
    await update.message.reply_text("🔄 All data and scheduled jobs have been reset.")

async def set_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Use format: /set_timezone Europe/Kyiv. Use /timezone_help for more info.")
        return

    tz_input = context.args[0].strip()
    tz_corrected = tz_input.replace(' ', '_').title()

    if tz_corrected not in pytz.all_timezones:
        await update.message.reply_text(f"⛔️ Invalid timezone: {tz_input}\nUse /timezone_help to see valid options.")
        return

    settings = load_settings()
    settings["timezone_name"] = tz_corrected
    save_settings(settings)

    await update.message.reply_text(f"🌍 Timezone set to {tz_corrected}")

async def timezone_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🕰 To set your timezone, use the command like this:\n"
        "`/set_timezone Europe/Kyiv`\n\n"
        "🔤 Timezone names are case-sensitive and must be in the format `Region/City`.\n"
        "Some common examples:\n"
        "- `Europe/Kyiv`\n"
        "- `Europe/London`\n"
        "- `America/New_York`\n"
        "- `Asia/Tokyo`\n"
        "- `Australia/Sydney`"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def post_init(app):
    scheduler.add_job(
        send_daily_summary,
        trigger='date',
        kwargs={"bot": app.bot, "chat_id": YOUR_CHAT_ID}
    )
    scheduler.start()

if __name__ == "__main__":
    create_db()

    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("manual_calc", manual_calc))
    app.add_handler(CommandHandler("set_time", set_time))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("set_timezone", set_timezone))
    app.add_handler(CommandHandler("timezone_help", timezone_help))
    print("🤖 Bot has started...")
    app.run_polling()
