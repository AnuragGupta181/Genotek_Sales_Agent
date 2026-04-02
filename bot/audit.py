"""
Audit trail module for Genotek Sales Support Bot.
Wraps every bot action with audit logging per SPEC.md CR-5.
"""

import logging
import time
from functools import wraps
from typing import Callable, Optional

from bot.supabase_client import SupabaseManager

logger = logging.getLogger(__name__)


class AuditTrail:
    """Manages audit logging for all bot actions."""

    def __init__(self, supabase: SupabaseManager):
        self.supabase = supabase

    def log(
        self,
        action_type: str,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        session_id: Optional[str] = None,
        input_text: Optional[str] = None,
        output_text: Optional[str] = None,
        warnings: Optional[list[str]] = None,
        model_used: Optional[str] = None,
        latency_ms: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Log an action to the audit trail."""
        return self.supabase.log_audit(
            action_type=action_type,
            user_id=user_id,
            username=username,
            session_id=session_id,
            input_text=input_text,
            output_text=output_text,
            warnings=warnings,
            model_used=model_used,
            latency_ms=latency_ms,
            metadata=metadata,
        )

    def log_message(
        self,
        user_id: int,
        username: Optional[str],
        session_id: str,
        input_text: str,
        output_text: str,
        model_used: str,
        latency_ms: int,
        warnings: Optional[list[str]] = None,
    ) -> dict:
        """Convenience method for logging a standard message exchange."""
        return self.log(
            action_type="MESSAGE",
            user_id=user_id,
            username=username,
            session_id=session_id,
            input_text=input_text,
            output_text=output_text,
            warnings=warnings,
            model_used=model_used,
            latency_ms=latency_ms,
        )

    def log_product_violation(
        self,
        user_id: int,
        username: Optional[str],
        session_id: str,
        input_text: str,
        warning: str,
        product_code: Optional[str] = None,
        suggested_alternative: Optional[str] = None,
    ) -> dict:
        """Log a product constraint violation."""
        return self.log(
            action_type="PRODUCT_CONSTRAINT_VIOLATION",
            user_id=user_id,
            username=username,
            session_id=session_id,
            input_text=input_text,
            output_text=warning,
            warnings=[warning],
            metadata={
                "product_code": product_code,
                "suggested_alternative": suggested_alternative,
            },
        )

    def log_pricing_escalation(
        self,
        user_id: int,
        username: Optional[str],
        session_id: str,
        input_text: str,
        authority: str,
        region: Optional[str] = None,
        reason: str = "",
    ) -> dict:
        """Log a pricing escalation routing decision."""
        return self.log(
            action_type="PRICING_ESCALATION",
            user_id=user_id,
            username=username,
            session_id=session_id,
            input_text=input_text,
            output_text=f"Routed to {authority}: {reason}",
            warnings=[f"Pricing escalated to {authority}"],
            metadata={"authority": authority, "region": region, "reason": reason},
        )

    def log_discount_escalation(
        self,
        user_id: int,
        username: Optional[str],
        session_id: str,
        input_text: str,
        authority: str,
        reason: str = "",
    ) -> dict:
        """Log a discount escalation."""
        return self.log(
            action_type="DISCOUNT_ESCALATION",
            user_id=user_id,
            username=username,
            session_id=session_id,
            input_text=input_text,
            output_text=f"Discount escalated to {authority}",
            warnings=[reason],
            metadata={"authority": authority, "reason": reason},
        )

    def log_model_route(
        self,
        user_id: int,
        session_id: str,
        input_text: str,
        model_used: str,
        tier: str,
        reason: str,
    ) -> dict:
        """Log which model was selected for a task."""
        return self.log(
            action_type="MODEL_ROUTE",
            user_id=user_id,
            session_id=session_id,
            input_text=input_text[:200],  # Truncate for routing log
            model_used=model_used,
            metadata={"tier": tier, "reason": reason},
        )

    def log_error(
        self,
        user_id: Optional[int],
        session_id: Optional[str],
        input_text: Optional[str],
        error: str,
    ) -> dict:
        """Log an error."""
        return self.log(
            action_type="ERROR",
            user_id=user_id,
            session_id=session_id,
            input_text=input_text,
            output_text=error,
            warnings=[error],
        )
