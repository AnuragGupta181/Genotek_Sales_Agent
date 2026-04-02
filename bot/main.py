"""
Genotek Sales Support Telegram Bot -- Entry Point.
Initializes all components and starts the bot.
"""

import logging
import sys

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

try:
    from bot.audit import AuditTrail
    from bot.config import Config
    from bot.graph import GenotekAgentGraph
    from bot.guardrails import Guardrails
    from bot.handlers import BotHandlers
    from bot.models import ModelRouter
    from bot.supabase_client import SupabaseManager
except ModuleNotFoundError:
    from audit import AuditTrail
    from config import Config
    from graph import GenotekAgentGraph
    from guardrails import Guardrails
    from handlers import BotHandlers
    from models import ModelRouter
    from supabase_client import SupabaseManager

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Initialize all components and start the Telegram bot."""

    # 1. Load and validate config
    config = Config()
    errors = config.validate()
    if errors:
        for err in errors:
            logger.error("Config error: %s", err)
        logger.error(
            "Fix the above configuration errors in your .env file and restart."
        )
        sys.exit(1)

    logger.info("Configuration loaded. USE_BEDROCK=%s", config.use_bedrock)

    # 2. Initialize Supabase
    supabase = SupabaseManager(config)
    logger.info("Supabase client initialized: %s", config.supabase_url)

    # 3. Initialize model router
    router = ModelRouter(config)
    logger.info("Model router initialized (Bedrock=%s)", config.use_bedrock)

    # 4. Initialize guardrails
    guardrails = Guardrails(supabase)
    logger.info("Guardrails initialized with product constraint cache")

    # 5. Initialize audit trail
    audit = AuditTrail(supabase)
    logger.info("Audit trail initialized")

    # 6. Build LangGraph workflow
    agent_graph = GenotekAgentGraph(
        supabase=supabase,
        model_router=router,
        guardrails=guardrails,
        audit=audit,
    )
    logger.info("LangGraph agent workflow compiled")

    # 7. Initialize Telegram handlers
    handlers = BotHandlers(agent_graph)

    # 8. Build Telegram application
    app = ApplicationBuilder().token(config.telegram_token).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help_command))
    app.add_handler(CommandHandler("products", handlers.products_command))
    app.add_handler(CommandHandler("escalation", handlers.escalation_command))
    app.add_handler(CommandHandler("status", handlers.status_command))

    # Register message handler (all text messages)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message)
    )

    # Register error handler
    app.add_error_handler(handlers.error_handler)

    # 9. Start polling
    logger.info("Starting Genotek Sales Support Bot (polling)...")
    logger.info("Trust Level: 0 (Information Only)")
    logger.info("Press Ctrl+C to stop")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
