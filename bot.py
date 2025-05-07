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

# Для ТЕСТУ: запускає через 2 хвилини після старту
#run_time = datetime.now() + timedelta(minutes=1)


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
    for job in scheduler.get_jobs():
        job.remove()

    trigger = CronTrigger(hour=hour, minute=minute)
    scheduler.add_job(send_daily_summary, trigger=trigger, kwargs={"bot": bot, "chat_id": chat_id})


async def send_daily_summary(bot, chat_id):
    summary = calculate_daily_summary()
    if not summary:
        logging.info(f"No data to send for chat {chat_id}")
        return  # нічого не надсилати

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

    if not context.args or not re.match(r"^\d{1,2}:\d{2}$", context.args[0]):
        await update.message.reply_text("⚠️ Use format: /set_time HH:MM (24h format)")
        return

    time_str = context.args[0]
    hour, minute = map(int, time_str.split(":"))

    if not (0 <= hour < 24 and 0 <= minute < 60):
        await update.message.reply_text("⛔️ Invalid time. Use HH:MM in 24h format.")
        return

    schedule_daily_summary(hour, minute, bot, chat_id)
    await update.message.reply_text(f"✅ Daily summary time set to {hour:02d}:{minute:02d}")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Зупиняємо всі задачі планувальника
    for job in scheduler.get_jobs():
        job.remove()

    # Очищаємо базу
    clear_db()

    # Повідомляємо користувача
    await update.message.reply_text("🔄 All data and scheduled jobs have been reset.")


async def set_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].lstrip("+-").isdigit():
        await update.message.reply_text("⚠️ Use format: /set_timezone +3 or /set_timezone -5")
        return

    offset = int(context.args[0])
    if not -12 <= offset <= 14:
        await update.message.reply_text("⛔️ Invalid timezone offset. Must be between -12 and +14.")
        return

    settings = load_settings()
    settings["timezone_offset"] = offset
    save_settings(settings)

    await update.message.reply_text(f"🌍 Timezone offset set to UTC{offset:+}")


async def post_init(app):
    scheduler.add_job(
        send_daily_summary,
        trigger='date',
        #run_date=run_time,
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


