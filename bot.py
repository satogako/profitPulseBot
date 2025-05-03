import logging
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

from db import create_db, save_to_db, calculate_daily_summary
from utils import parse_pnl_message

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

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

if __name__ == "__main__":
    create_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("manual_calc", manual_calc))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot has started...")
    app.run_polling()
