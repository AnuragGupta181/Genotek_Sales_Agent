import os
import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic
from supabase import create_client, Client


# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Clients ───────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_KEY   = os.environ["ANTHROPIC_API_KEY"]
SUPABASE_URL    = os.environ["SUPABASE_URL"]
SUPABASE_KEY    = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

claude_client: anthropic.Anthropic     = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
supabase: Client                        = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── In-process conversation history (per chat_id) ─────────────────────────────
# Keeps the last N turns so Claude has context within a session.
MAX_HISTORY = 10
conversation_histories: dict[int, list[dict]] = {}


# ── Supabase helpers ─────────────────────────────────────────────────────────
def log_turn(
    chat_id: int,
    username: str,
    user_message: str,
    bot_reply: str,
    model: str = "claude-sonnet-4-20250514",
    latency_ms: int | None = None,
) -> None:
    """Insert one conversation turn into the `conversations` table."""
    try:
        supabase.table("conversations").insert(
            {
                "chat_id":      str(chat_id),
                "username":     username,
                "user_message": user_message,
                "bot_reply":    bot_reply,
                "model":        model,
                "latency_ms":   latency_ms,
                "created_at":   datetime.now(timezone.utc).isoformat(),
            }
        ).execute()
    except Exception as exc:
        logger.error("Supabase insert failed: %s", exc)


# ── Telegram handlers ─────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Hey! I'm powered by Claude.\n\n"
        "Just send me any message and I'll reply. "
        "I remember our conversation for this session.\n\n"
        "Commands:\n"
        "  /start  – this message\n"
        "  /clear  – reset conversation history\n"
        "  /help   – tips"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "💡 Tips:\n"
        "• Ask me anything — coding, writing, analysis.\n"
        "• I remember context within a session (last 10 turns).\n"
        "• Use /clear to start fresh."
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    conversation_histories.pop(chat_id, None)
    await update.message.reply_text("🗑️ Conversation history cleared. Fresh start!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id    = update.effective_chat.id
    user_text  = update.message.text.strip()
    username   = update.effective_user.username or update.effective_user.full_name or str(chat_id)

    # Show "typing…" indicator while we wait for Claude
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Build / retrieve history for this chat
    history = conversation_histories.setdefault(chat_id, [])
    history.append({"role": "user", "content": user_text})

    # Trim to last MAX_HISTORY messages (keep pairs)
    if len(history) > MAX_HISTORY * 2:
        conversation_histories[chat_id] = history[-(MAX_HISTORY * 2):]
        history = conversation_histories[chat_id]

    # ── Call Claude ────────────────────────────────────────────────────────────
    start_ts = datetime.now(timezone.utc)
    try:
        response = claude_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=(
                "You are a helpful, concise Telegram bot assistant. "
                "Keep replies short and clear unless the user explicitly wants detail. "
                "Use plain text — no Markdown."
            ),
            messages=history,
        )
        reply_text = response.content[0].text
    except anthropic.APIError as exc:
        logger.error("Anthropic API error: %s", exc)
        reply_text = "⚠️ Claude API error — please try again in a moment."

    latency_ms = int((datetime.now(timezone.utc) - start_ts).total_seconds() * 1000)

    # Append assistant turn to history
    history.append({"role": "assistant", "content": reply_text})

    # ── Send reply ─────────────────────────────────────────────────────────────
    await update.message.reply_text(reply_text)

    # ── Log to Supabase (non-blocking best-effort) ─────────────────────────────
    log_turn(
        chat_id=chat_id,
        username=username,
        user_message=user_text,
        bot_reply=reply_text,
        latency_ms=latency_ms,
    )


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help",  help_command))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running… (polling)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
