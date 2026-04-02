"""
Telegram message handlers for Genotek Sales Support Bot.
Connects python-telegram-bot to the LangGraph workflow.
"""

import hashlib
import logging
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from bot.graph import GenotekAgentGraph

logger = logging.getLogger(__name__)


def _session_id(user_id: int) -> str:
    """Generate a stable session ID for a user.
    In production, sessions could rotate daily or per-conversation.
    For MVP, one session per user keeps context persistent.
    """
    return hashlib.sha256(f"genotek-{user_id}".encode()).hexdigest()[:16]


class BotHandlers:
    """Telegram bot handler class wiring updates to the LangGraph agent."""

    def __init__(self, agent_graph: GenotekAgentGraph):
        self.agent = agent_graph

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        user = update.effective_user
        welcome = (
            f"Hello {user.first_name}, welcome to the Genotek Sales Support Agent.\n\n"
            "I can help with:\n"
            "- Classifying RFQs by region and product\n"
            "- Routing pricing requests to the right authority\n"
            "- Checking product application constraints\n"
            "- Tracking follow-up status\n"
            "- Supplier lead time information\n\n"
            "IMPORTANT: I never set prices, approve discounts, or commit delivery dates. "
            "All pricing decisions require human authority.\n\n"
            "Type your question or paste an RFQ to get started."
        )
        await update.message.reply_text(welcome)

    async def help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /help command."""
        help_text = (
            "Genotek Sales Support Agent -- Commands:\n\n"
            "/start - Welcome message\n"
            "/help - This help text\n"
            "/products - List available product families\n"
            "/escalation - Show pricing escalation matrix\n"
            "/status - Bot status and model info\n\n"
            "Just type naturally to:\n"
            "- Ask about products (e.g., 'Tell me about WTZ-1800')\n"
            "- Route pricing (e.g., 'Need pricing for UAE project')\n"
            "- Check constraints (e.g., 'Can I use WTZ-1800 for a pool?')\n"
            "- Get supplier info (e.g., 'RY Extrusion lead times')\n"
        )
        await update.message.reply_text(help_text)

    async def products_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /products command."""
        products_text = (
            "Genotek Product Families:\n\n"
            "WTZ Series - Expansion Joint Covers\n"
            "  WTZ-1200: Standard (above-waterline)\n"
            "  WTZ-1800: Wall/ceiling (above-waterline ONLY)\n"
            "  WTZ-2400: Waterproof (submersible rated)\n"
            "  WTZ-3000: Heavy duty floor (vehicle traffic)\n\n"
            "EJ Series - Specialty Joints\n"
            "  EJ-AL300: Aluminum profile (custom dies, 75-85 day lead)\n"
            "  EJ-RB200: EPDM rubber profile\n\n"
            "FB Series - Fire Barriers\n"
            "  EJ-FB100: 2-hour fire rated\n"
            "  FB-SS304: SS304 stainless, 4-hour rated\n\n"
            "Note: Always verify product suitability for your specific application. "
            "Some products have environment restrictions."
        )
        await update.message.reply_text(products_text)

    async def escalation_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /escalation command."""
        matrix = (
            "Pricing Escalation Matrix:\n\n"
            "UAE items < AED 100/LM -> Shylesh (auto-approve)\n"
            "KSA deals > SAR 500K  -> Bijoy (large deal)\n"
            "India (all)           -> Niranjan (Pidilite)\n"
            "Discount > 15%        -> Bijoy ALWAYS\n"
            "Turkey custom         -> Ankara Factory\n"
            "International/Other   -> Bijoy (strategic)\n\n"
            "Follow-Up Cadence:\n"
            "Day 3  -> Confirm receipt\n"
            "Day 7  -> Specs/pricing questions\n"
            "Day 14 -> Timeline for decision\n"
            "Day 30 -> Escalate to Bijoy\n"
            "Day 96 -> Deal considered dead"
        )
        await update.message.reply_text(matrix)

    async def status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /status command."""
        status = (
            "Bot Status: ONLINE\n"
            "Trust Level: 0 (Information Only)\n\n"
            "Model Routing:\n"
            "  Haiku  (~80%) - Triage, classification\n"
            "  Sonnet (~15%) - Quote drafting, routing\n"
            "  Opus   (~5%)  - Complex pricing logic\n\n"
            "Backend: AWS Bedrock\n"
            "Storage: Supabase + pgvector\n"
            "Framework: LangGraph + LangChain"
        )
        await update.message.reply_text(status)

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle all text messages through the LangGraph workflow."""
        user = update.effective_user
        message_text = update.message.text

        if not message_text or not message_text.strip():
            await update.message.reply_text("Please send a text message.")
            return

        session_id = _session_id(user.id)

        # Show typing indicator
        await update.message.chat.send_action("typing")

        # Process through LangGraph
        result = self.agent.process_message(
            user_message=message_text,
            user_id=user.id,
            username=user.username,
            session_id=session_id,
        )

        response = result["response"]

        # Append model info in debug mode
        warnings = result.get("warnings", [])
        if warnings:
            warning_text = "\n".join(f"[!] {w}" for w in warnings)
            response = f"{warning_text}\n\n{response}"

        # Telegram has a 4096 char limit per message
        if len(response) > 4000:
            # Split into chunks
            for i in range(0, len(response), 4000):
                chunk = response[i : i + 4000]
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text(response)

    async def error_handler(
        self, update: object, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Global error handler for the bot."""
        logger.error("Update %s caused error: %s", update, context.error)
        if isinstance(update, Update) and update.message:
            await update.message.reply_text(
                "An error occurred while processing your request. "
                "This has been logged. Please try again."
            )
