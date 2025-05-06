import logging
import asyncio
import os
import re
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from db import create_db, save_to_db, calculate_daily_summary, clear_db
from apscheduler.schedulers.background import BackgroundScheduler
from telegram.constants import ParseMode
from utils import parse_pnl_message
from datetime import datetime, timedelta

# Для ТЕСТУ: запускає через 2 хвилини після старту
run_time = datetime.now() + timedelta(minutes=1)


load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
YOUR_CHAT_ID = int(os.getenv("YOUR_CHAT_ID"))
scheduler = BackgroundScheduler()


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)


def schedule_daily_summary(hour: int, minute: int, bot, chat_id):
    # Видаляємо старі задачі
    for job in scheduler.get_jobs():
        job.remove()

    trigger = CronTrigger(hour=hour, minute=minute)
    scheduler.add_job(send_daily_summary, trigger=trigger, args=[bot, chat_id])


def send_daily_summary(bot, chat_id):
    summary = calculate_daily_summary()
    if not summary:
        return

    msg = "📊 Daily Summary:\n"
    for currency, data in summary.items():
        msg += (
            f"\n💰 *{currency}*\n"
            f"🟢 Profit: `{data['profit']:.4f}`\n"
            f"🔴 Loss: `{data['loss']:.4f}`\n"
            f"📈 Net: `{data['net']:.4f}`\n"
        )

    asyncio.run(bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.MARKDOWN))
    clear_db()



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I am a bot for tracking profit 💰")


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


if __name__ == "__main__":
    create_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("manual_calc", manual_calc))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot has started...")
    app.add_handler(CommandHandler("set_time", set_time))
    scheduler.add_job(send_daily_summary, 'date', run_date=run_time, args=[app.bot, YOUR_CHAT_ID])
    scheduler.start()
    app.run_polling()