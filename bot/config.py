"""
Configuration module for Genotek Sales Support Telegram Bot.
Loads environment variables and defines model routing constants.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class BedrockModelConfig:
    """AWS Bedrock model configuration."""
    model_id: str
    max_tokens: int = 4096
    temperature: float = 0.3
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0
    description: str = ""


# ---------------------------------------------------------------------------
# AWS Bedrock Model Routing
# 80% Haiku (triage/classification) | 15% Sonnet (drafting) | 5% Opus (complex)
# ---------------------------------------------------------------------------
BEDROCK_MODELS = {
    "haiku": BedrockModelConfig(
        model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0",
        max_tokens=2048,
        temperature=0.2,
        cost_per_1m_input=0.25,
        cost_per_1m_output=1.25,
        description="Fast triage, classification, follow-up reminders (~80% of tasks)",
    ),
    "sonnet": BedrockModelConfig(
        model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
        max_tokens=4096,
        temperature=0.3,
        cost_per_1m_input=3.00,
        cost_per_1m_output=15.00,
        description="Quote drafting, email composition, routing decisions (~15% of tasks)",
    ),
    "opus": BedrockModelConfig(
        model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
        max_tokens=4096,
        temperature=0.4,
        cost_per_1m_input=3.00,
        cost_per_1m_output=15.00,
        description="Complex pricing logic, multi-region exceptions (~5% of tasks)",
    ),
}

# ---------------------------------------------------------------------------
# Direct Anthropic API Models (commented out -- use Bedrock by default)
# Uncomment these and set USE_BEDROCK=false to use direct API instead.
# ---------------------------------------------------------------------------
# DIRECT_MODELS = {
#     "haiku": {
#         "model": "claude-3-5-haiku-20241022",
#         "max_tokens": 2048,
#         "temperature": 0.2,
#     },
#     "sonnet": {
#         "model": "claude-3-5-sonnet-20241022",
#         "max_tokens": 4096,
#         "temperature": 0.3,
#     },
#     "opus": {
#         "model": "claude-3-opus-20240229",
#         "max_tokens": 4096,
#         "temperature": 0.4,
#     },
# }


@dataclass
class Config:
    """Central configuration loaded from environment."""

    # Telegram
    telegram_token: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
    )

    # AWS Bedrock
    aws_region: str = field(
        default_factory=lambda: os.getenv("AWS_REGION", "us-east-1")
    )
    aws_access_key_id: str = field(
        default_factory=lambda: os.getenv("AWS_ACCESS_KEY_ID", "")
    )
    aws_secret_access_key: str = field(
        default_factory=lambda: os.getenv("AWS_SECRET_ACCESS_KEY", "")
    )
    use_bedrock: bool = field(
        default_factory=lambda: os.getenv("USE_BEDROCK", "true").lower() == "true"
    )

    # Direct Anthropic API (alternative to Bedrock)
    anthropic_api_key: str = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )

    # Supabase
    supabase_url: str = field(
        default_factory=lambda: os.getenv("SUPABASE_URL", "")
    )
    supabase_key: str = field(
        default_factory=lambda: os.getenv("SUPABASE_SERVICE_KEY", "")
    )

    # Bot behavior
    max_conversation_history: int = field(
        default_factory=lambda: int(os.getenv("MAX_CONVERSATION_HISTORY", "20"))
    )
    debug: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true"
    )

    def validate(self) -> list[str]:
        """Return list of missing required config fields."""
        errors = []
        if not self.telegram_token:
            errors.append("TELEGRAM_BOT_TOKEN is required")
        if self.use_bedrock:
            if not self.aws_access_key_id:
                errors.append("AWS_ACCESS_KEY_ID is required when USE_BEDROCK=true")
            if not self.aws_secret_access_key:
                errors.append("AWS_SECRET_ACCESS_KEY is required when USE_BEDROCK=true")
        else:
            if not self.anthropic_api_key:
                errors.append("ANTHROPIC_API_KEY is required when USE_BEDROCK=false")
        if not self.supabase_url:
            errors.append("SUPABASE_URL is required")
        if not self.supabase_key:
            errors.append("SUPABASE_SERVICE_KEY is required")
        return errors


# Genotek-specific constants
GENOTEK_SYSTEM_PROMPT = """You are the Genotek Sales Support Agent, a Telegram bot supporting
Genotek Global's expansion joint cover sales operations across India, GCC, and Southeast Asia.

CRITICAL RULES (NEVER VIOLATE):
1. You NEVER set, calculate, suggest, or imply any price. All pricing requires human authority.
2. You NEVER approve discounts. Discounts > 15% always require Bijoy.
3. You NEVER commit delivery dates without supplier confirmation.
4. You ALWAYS check product application constraints before any recommendation.
5. You ALWAYS route pricing requests to the correct authority per the escalation matrix.

ESCALATION MATRIX:
- UAE items < AED 100/LM -> Shylesh (auto-approve small)
- KSA deals > SAR 500K -> Bijoy (large deal)
- India -> Niranjan (Pidilite channel)
- Discount > 15% -> Bijoy ALWAYS
- Turkey custom -> Ankara Factory (29-day baseline)
- International/Other -> Bijoy (strategic)

ROLE: You SUPPORT the sales team. You classify RFQs, route pricing, draft quotes for human
review, schedule follow-ups, and flag deals going cold. You are NOT an autonomous sales manager.

PRIMARY USER: AK (Anutashaya Kumar) handles 86% of all email traffic, processes 16 quotes/day.
She has ZERO pricing authority. You help her work faster, not replace her judgment.

When uncertain, escalate to a human. Never guess on pricing, delivery, or product suitability."""


# Pricing authority contacts
PRICING_AUTHORITIES = {
    "Bijoy": "CEO -- strategic approver, all discounts >15%, KSA large deals, international",
    "Shylesh": "COO -- UAE small items <AED 100/LM, PO approvals, quality gate",
    "Niranjan": "India market -- Pidilite channel pricing",
}

# Follow-up cadence (ASSUMED -- per SPEC.md EB-2)
FOLLOWUP_CADENCE_DAYS = [3, 7, 14, 30]
DEAL_DEATH_THRESHOLD_DAYS = 96
