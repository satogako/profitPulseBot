import logging
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# Load environment variables (like bot token)
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Enable logging (useful for debugging)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# Handler for the /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username or "unknown user"
    print(f"Received /start from user: {username}")
    await update.message.reply_text("Hello! I am a bot for tracking profit 💰")

# Main section — bot launch
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("🤖 Bot has started...")
    app.run_polling()
