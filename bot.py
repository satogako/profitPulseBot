import os
import re
import json
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from telegram.constants import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from db import create_db, save_to_db, calculate_daily_summary, clear_db
from utils import parse_pnl_message

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
YOUR_CHAT_ID = int(os.getenv("YOUR_CHAT_ID"))
SETTINGS_FILE = "settings.json"

scheduler = AsyncIOScheduler()

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

def schedule_daily_summary(local_hour: int, minute: int, bot, chat_id):
    settings = load_settings()
    tz_name = settings.get("timezone")
    if not tz_name:
        logging.warning("Timezone not set.")
        return

    try:
        tz = ZoneInfo(tz_name)
    except Exception as e:
        logging.error(f"Invalid timezone: {tz_name}")
        return

    now_local = datetime.now(tz)
    target_time_local = now_local.replace(hour=local_hour, minute=minute, second=0, microsecond=0)
    if target_time_local <= now_local:
        target_time_local += timedelta(days=1)

    target_time_utc = target_time_local.astimezone(ZoneInfo("UTC"))

    for job in scheduler.get_jobs():
        job.remove()

    trigger = CronTrigger(hour=target_time_utc.hour, minute=target_time_utc.minute, timezone=ZoneInfo("UTC"))

    scheduler.add_job(
        send_daily_summary,
        trigger=trigger,
        kwargs={"bot": bot, "chat_id": chat_id}
    )

    logging.info(f"📅 Daily summary scheduled for {target_time_utc.strftime('%Y-%m-%d %H:%M')} UTC")
    logging.info(f"⏰ Local time: {target_time_local.strftime('%Y-%m-%d %H:%M')} ({tz_name})")

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
    if "timezone" not in settings:
        await update.message.reply_text("🌍 Please set your timezone first using /set_timezone Europe/Kyiv")
        return

    if not context.args or not re.match(r"^\d{1,2}:\d{2}$", context.args[0]):
        await update.message.reply_text("⚠️ Use format: /set_time HH:MM (24h format)")
        return

    hour, minute = map(int, context.args[0].split(":"))
    if not (0 <= hour < 24 and 0 <= minute < 60):
        await update.message.reply_text("⛔️ Invalid time. Use HH:MM in 24h format.")
        return

    schedule_daily_summary(hour, minute, bot, chat_id)
    await update.message.reply_text(f"✅ Daily summary time set to {hour:02d}:{minute:02d} (your local time)")

async def set_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Use format: /set_timezone Europe/Kyiv")
        return

    tz_name = context.args[0]
    try:
        _ = ZoneInfo(tz_name)
    except Exception:
        await update.message.reply_text("⛔️ Invalid timezone name. Try something like Europe/Kyiv or America/New_York")
        return

    settings = load_settings()
    settings["timezone"] = tz_name
    save_settings(settings)
    await update.message.reply_text(f"🌍 Timezone set to {tz_name}")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for job in scheduler.get_jobs():
        job.remove()
    clear_db()
    await update.message.reply_text("🔄 All data and scheduled jobs have been reset.")

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

    print("🤖 Bot has started...")
    app.run_polling()
