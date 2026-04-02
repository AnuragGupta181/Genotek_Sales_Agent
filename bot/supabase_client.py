"""
Supabase client module for Genotek Sales Support Bot.
Handles all database operations: conversations, audit logs, products, embeddings.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from supabase import create_client, Client

from bot.config import Config

logger = logging.getLogger(__name__)


class SupabaseManager:
    """Manages all Supabase operations for the bot."""

    def __init__(self, config: Config):
        self.client: Client = create_client(config.supabase_url, config.supabase_key)

    # -------------------------------------------------------------------------
    # Conversations
    # -------------------------------------------------------------------------
    def store_conversation_turn(
        self,
        user_id: int,
        username: Optional[str],
        session_id: str,
        role: str,
        content: str,
        model_used: Optional[str] = None,
        tokens_input: Optional[int] = None,
        tokens_output: Optional[int] = None,
        cost_estimate: Optional[float] = None,
        metadata: Optional[dict] = None,
        embedding: Optional[list[float]] = None,
    ) -> dict:
        """Store a single conversation turn. Returns the inserted row."""
        row = {
            "user_id": user_id,
            "username": username,
            "session_id": session_id,
            "role": role,
            "content": content,
            "model_used": model_used,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "cost_estimate": cost_estimate,
            "metadata": metadata or {},
        }
        if embedding is not None:
            row["embedding"] = embedding

        result = self.client.table("conversations").insert(row).execute()
        logger.debug("Stored conversation turn: user=%s role=%s", user_id, role)
        return result.data[0] if result.data else {}

    def get_conversation_history(
        self, user_id: int, session_id: str, limit: int = 20
    ) -> list[dict]:
        """Retrieve recent conversation history for context window."""
        result = (
            self.client.table("conversations")
            .select("role, content, model_used, created_at")
            .eq("user_id", user_id)
            .eq("session_id", session_id)
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        return result.data or []

    # -------------------------------------------------------------------------
    # Audit Log
    # -------------------------------------------------------------------------
    def log_audit(
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
        """Log an action to bot_audit_log. Every bot action must call this."""
        row = {
            "action_type": action_type,
            "user_id": user_id,
            "username": username,
            "session_id": session_id,
            "input_text": input_text,
            "output_text": output_text,
            "warnings": warnings or [],
            "model_used": model_used,
            "latency_ms": latency_ms,
            "metadata": metadata or {},
        }
        try:
            result = self.client.table("bot_audit_log").insert(row).execute()
            logger.debug("Audit logged: action=%s user=%s", action_type, user_id)
            return result.data[0] if result.data else {}
        except Exception as e:
            # Audit logging failure is critical but should not crash the bot
            logger.error("AUDIT LOG FAILURE: %s -- %s", action_type, e)
            return {}

    # -------------------------------------------------------------------------
    # Products
    # -------------------------------------------------------------------------
    def get_product(self, product_code: str) -> Optional[dict]:
        """Look up a product by its code."""
        result = (
            self.client.table("products")
            .select("*")
            .eq("product_code", product_code.upper())
            .eq("is_active", True)
            .execute()
        )
        return result.data[0] if result.data else None

    def get_all_products(self) -> list[dict]:
        """Retrieve all active products."""
        result = (
            self.client.table("products")
            .select("*")
            .eq("is_active", True)
            .execute()
        )
        return result.data or []

    def search_products_by_family(self, family: str) -> list[dict]:
        """Search products by product family code."""
        result = (
            self.client.table("products")
            .select("*")
            .eq("product_family", family.upper())
            .eq("is_active", True)
            .execute()
        )
        return result.data or []

    # -------------------------------------------------------------------------
    # Suppliers
    # -------------------------------------------------------------------------
    def get_supplier(self, name: str) -> Optional[dict]:
        """Look up supplier by name."""
        result = (
            self.client.table("suppliers")
            .select("*")
            .ilike("name", f"%{name}%")
            .eq("is_active", True)
            .execute()
        )
        return result.data[0] if result.data else None

    # -------------------------------------------------------------------------
    # Pricing Rules
    # -------------------------------------------------------------------------
    def get_pricing_rules(self, region: Optional[str] = None) -> list[dict]:
        """Get pricing escalation rules, optionally filtered by region."""
        query = self.client.table("pricing_rules").select("*")
        if region:
            query = query.or_(f"region.eq.{region},region.eq.ANY")
        result = query.execute()
        return result.data or []

    # -------------------------------------------------------------------------
    # Embeddings Search
    # -------------------------------------------------------------------------
    def search_similar_conversations(
        self,
        query_embedding: list[float],
        match_threshold: float = 0.7,
        match_count: int = 10,
    ) -> list[dict]:
        """Search conversations by embedding similarity using pgvector."""
        try:
            result = self.client.rpc(
                "match_conversations",
                {
                    "query_embedding": query_embedding,
                    "match_threshold": match_threshold,
                    "match_count": match_count,
                },
            ).execute()
            return result.data or []
        except Exception as e:
            logger.error("Embedding search failed: %s", e)
            return []
