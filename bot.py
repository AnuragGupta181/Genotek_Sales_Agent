"""
Bijon Telegram Bot — V2.1
Guardrails + product constraint checking + full audit logging.
See SPEC.md for correctness rules before reading this code.
"""

import os
import re
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic
from supabase import create_client, Client

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Environment ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_KEY  = os.environ["ANTHROPIC_API_KEY"]
SUPABASE_URL   = os.environ["SUPABASE_URL"]
SUPABASE_KEY   = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
ESCALATION_QUOTE_LIMIT = float(os.getenv("ESCALATION_QUOTE_LIMIT", "500000"))

# ── Clients ───────────────────────────────────────────────────────────────────
claude:   anthropic.Anthropic = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
supabase: Client              = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── In-process conversation history ──────────────────────────────────────────
MAX_HISTORY = 10
conversation_histories: dict[int, list[dict]] = {}

# ── Compliance keywords → always escalate ─────────────────────────────────────
COMPLIANCE_KEYWORDS = [
    "fire rating", "fire resistance", "is code", "bis", "nbc", "load rating",
    "structural", "seismic", "tensile strength", "regulatory", "certification",
    "approval", "codal", "standard compliance",
]

QUOTE_PATTERN        = re.compile(r"\b(quote|quotation|price|cost|rate|estimate)\b", re.I)
PRODUCT_CODE_PATTERN = re.compile(r"\b([A-Z]{2,5}-\d{3,5}[A-Z]?)\b")


# ── Audit logging ─────────────────────────────────────────────────────────────
def audit_log(chat_id, username, action_type, input_text, output_text="",
              warnings=None, product_code=None, quote_value=None, escalated=False):
    try:
        supabase.table("bot_audit_log").insert({
            "chat_id":      str(chat_id),
            "username":     username,
            "action_type":  action_type,
            "input_text":   input_text,
            "output_text":  output_text,
            "warnings":     warnings or [],
            "product_code": product_code,
            "quote_value":  quote_value,
            "escalated":    escalated,
            "created_at":   datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as exc:
        logger.error("audit_log failed: %s", exc)


def log_conversation(chat_id, username, user_message, bot_reply, latency_ms):
    try:
        supabase.table("conversations").insert({
            "chat_id":      str(chat_id),
            "username":     username,
            "user_message": user_message,
            "bot_reply":    bot_reply,
            "model":        "claude-sonnet-4-20250514",
            "latency_ms":   latency_ms,
            "created_at":   datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as exc:
        logger.error("conversations insert failed: %s", exc)


# ── Product guardrail ─────────────────────────────────────────────────────────
def check_product_eligibility(product_code: str, application_description: str) -> dict:
    """
    Fetches product from Supabase and checks disallowed_applications
    against the user's application description. Returns eligibility dict.
    """
    try:
        result = (
            supabase.table("products")
            .select("*")
            .eq("product_code", product_code.upper())
            .eq("is_active", True)
            .execute()
        )
    except Exception as exc:
        logger.error("Products query failed: %s", exc)
        return {"found": False, "allowed": False, "product": None,
                "triggered_keyword": None, "constraint_note": None}

    if not result.data:
        return {"found": False, "allowed": False, "product": None,
                "triggered_keyword": None, "constraint_note": None}

    product   = result.data[0]
    app_lower = application_description.lower()
    triggered = next(
        (kw for kw in (product.get("disallowed_applications") or []) if kw.lower() in app_lower),
        None,
    )
    return {
        "found":             True,
        "allowed":           triggered is None,
        "product":           product,
        "triggered_keyword": triggered,
        "constraint_note":   product.get("constraint_note"),
    }


def is_compliance_query(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in COMPLIANCE_KEYWORDS)


# ── Core message handler ──────────────────────────────────────────────────────
async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id   = update.effective_chat.id
    user_text = update.message.text.strip()
    username  = (update.effective_user.username
                 or update.effective_user.full_name
                 or str(chat_id))

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # 1. Compliance escalation (CR-05)
    if is_compliance_query(user_text):
        reply = (
            "⚠️ This involves regulatory/engineering compliance (fire ratings, IS codes, "
            "structural loads). These require a qualified engineer.\n\n"
            "Flagging for our technical team — someone will follow up."
        )
        audit_log(chat_id, username, "COMPLIANCE_QUERY", user_text, reply,
                  warnings=["Compliance keyword detected"], escalated=True)
        await update.message.reply_text(reply)
        return

    # 2. Product guardrail (CR-01, FM-01, FM-03)
    codes            = PRODUCT_CODE_PATTERN.findall(user_text)
    is_quote_request = bool(QUOTE_PATTERN.search(user_text)) or (
        codes and any(w in user_text.lower()
                      for w in ["quote", "price", "cost", "rate", "estimate", "how much"])
    )

    if is_quote_request and codes:
        for code in codes:
            check = check_product_eligibility(code, user_text)

            # Product not in DB (FM-02)
            if not check["found"]:
                reply = (
                    f"❌ Product `{code}` not found in our database.\n"
                    "Cannot generate a quotation for an unknown code. "
                    "Please verify or contact our team."
                )
                audit_log(chat_id, username, "PRODUCT_NOT_FOUND", user_text, reply,
                          product_code=code, escalated=True,
                          warnings=[f"{code} not in products table"])
                await update.message.reply_text(reply)
                return

            # Disallowed application (FM-01, FM-03)
            if not check["allowed"]:
                p    = check["product"]
                kw   = check["triggered_keyword"]
                note = check["constraint_note"] or "This product has application restrictions."
                reply = (
                    f"🚫 *Guardrail triggered — {code}*\n\n"
                    f"{note}\n\n"
                    f'Your request mentions *"{kw}"* — a disallowed application for {code}.\n\n'
                    f"✅ Allowed: {', '.join(p['application_scope'])}\n\n"
                    "Escalating to our technical team for the correct product recommendation."
                )
                audit_log(chat_id, username, "GUARDRAIL_TRIGGERED", user_text, reply,
                          product_code=code, escalated=True,
                          warnings=[f"Disallowed keyword: {kw}", f"Constraint: {note}"])
                await update.message.reply_text(reply, parse_mode="Markdown")
                return

            # Valid quote
            p          = check["product"]
            unit_price = float(p["unit_price"])
            reply = (
                f"✅ *Quotation — {code}*\n"
                f"*{p['product_name']}*\n\n"
                f"Unit Price: ₹{unit_price:,.2f} / {p['unit']}\n"
                f"Application scope: {', '.join(p['application_scope'])}\n\n"
                f"_{p['description']}_\n\n"
                "📌 Indicative price — final quote subject to site survey and quantity."
            )
            est_value   = unit_price * 10
            escalated   = est_value >= ESCALATION_QUOTE_LIMIT
            action_type = "HIGH_VALUE_ESCALATION" if escalated else "QUOTE_GENERATED"
            if escalated:
                reply += "\n\n⚠️ High-value order — requires human sign-off. Our team will contact you."

            audit_log(chat_id, username, action_type, user_text, reply,
                      product_code=code, quote_value=est_value, escalated=escalated)
            log_conversation(chat_id, username, user_text, reply, 0)
            await update.message.reply_text(reply, parse_mode="Markdown")
            return

    # 3. General LLM response
    history = conversation_histories.setdefault(chat_id, [])
    history.append({"role": "user", "content": user_text})
    if len(history) > MAX_HISTORY * 2:
        conversation_histories[chat_id] = history[-(MAX_HISTORY * 2):]
        history = conversation_histories[chat_id]

    start_ts = datetime.now(timezone.utc)
    try:
        response = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=(
                "You are a helpful assistant for Bijon, a construction products company. "
                "Help customers with product info and project requirements. "
                "Plain text only — no Markdown. Never invent product specs or prices. "
                "Escalate compliance or engineering questions to the human team."
            ),
            messages=history,
        )
        reply = response.content[0].text
    except anthropic.APIError as exc:
        logger.error("Claude API error: %s", exc)
        reply = "⚠️ Couldn't reach AI service. Please try again."
        audit_log(chat_id, username, "ERROR", user_text, reply, warnings=[str(exc)])
        await update.message.reply_text(reply)
        return

    latency_ms = int((datetime.now(timezone.utc) - start_ts).total_seconds() * 1000)
    history.append({"role": "assistant", "content": reply})

    audit_log(chat_id, username, "LLM_RESPONSE", user_text, reply)
    log_conversation(chat_id, username, user_text, reply, latency_ms)
    await update.message.reply_text(reply)


# ── Command handlers ──────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Hi! I'm Bijon's product assistant.\n\n"
        "I can help with product info and indicative quotations.\n"
        "All actions are logged for quality assurance.\n\n"
        "/start  – this message\n"
        "/clear  – reset conversation\n"
        "/help   – usage tips"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "💡 Tips:\n"
        "• Ask about products by code (e.g. WTZ-1800)\n"
        "• Request quotes: 'Quote WTZ-3400S for pool joint'\n"
        "• I'll flag wrong-application requests automatically\n"
        "• Compliance questions go to our engineering team\n"
        "• /clear to start fresh"
    )

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conversation_histories.pop(update.effective_chat.id, None)
    await update.message.reply_text("🗑️ Conversation reset.")


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help",  help_command))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))
    logger.info("Bijon Bot V2.1 running…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()