import os
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    filters,
    ContextTypes,
)

from google import genai
from supabase import create_client

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

# Clients
client = genai.Client(api_key=GEMINI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user_message = update.message.text
    user_id = str(update.message.from_user.id)

    try:
        # Call LLM
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=user_message
        )

        bot_reply = response.text

        # Save to Supabase
        supabase.table("messages").insert({
            "user_id": user_id,
            "user_message": user_message,
            "bot_response": bot_reply
        }).execute()

        # Send reply
        await update.message.reply_text(bot_reply)

    except Exception as e:
        await update.message.reply_text(
            f"Error: {str(e)}"
        )


def main():

    app = ApplicationBuilder().token(
        TELEGRAM_TOKEN
    ).build()

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    print("Bot running...")

    app.run_polling()


if __name__ == "__main__":
    main()