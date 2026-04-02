"""
LangGraph workflow for Genotek Sales Support Bot.
Implements a stateful graph: Classify -> Guardrails -> Route Model -> Generate -> Audit.
Uses LangChain + LangGraph for orchestration with Supabase embeddings.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Annotated, Any, Optional, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from bot.audit import AuditTrail
from bot.config import GENOTEK_SYSTEM_PROMPT
from bot.guardrails import Guardrails
from bot.models import ModelRouter, ModelTier
from bot.supabase_client import SupabaseManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State schema for the LangGraph workflow
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    """State passed through the LangGraph workflow nodes."""

    # Input
    user_message: str
    user_id: int
    username: Optional[str]
    session_id: str

    # Conversation history (LangChain message format)
    messages: Annotated[list, add_messages]

    # Guardrail results
    guardrail_warnings: list[str]
    has_violation: bool
    violation_response: Optional[str]

    # Model routing
    model_tier: Optional[str]
    model_id: Optional[str]
    routing_reason: Optional[str]

    # Output
    response: Optional[str]
    model_used: Optional[str]
    tokens_input: int
    tokens_output: int
    cost_estimate: float
    latency_ms: int


# ---------------------------------------------------------------------------
# Workflow builder
# ---------------------------------------------------------------------------
class GenotekAgentGraph:
    """Builds and runs the LangGraph workflow for processing messages."""

    def __init__(
        self,
        supabase: SupabaseManager,
        model_router: ModelRouter,
        guardrails: Guardrails,
        audit: AuditTrail,
    ):
        self.supabase = supabase
        self.router = model_router
        self.guardrails = guardrails
        self.audit = audit
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine."""
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("load_history", self._node_load_history)
        workflow.add_node("run_guardrails", self._node_run_guardrails)
        workflow.add_node("route_model", self._node_route_model)
        workflow.add_node("generate_response", self._node_generate_response)
        workflow.add_node("handle_violation", self._node_handle_violation)
        workflow.add_node("store_and_audit", self._node_store_and_audit)

        # Define edges
        workflow.set_entry_point("load_history")
        workflow.add_edge("load_history", "run_guardrails")

        # Conditional: if violation, handle it; otherwise route to model
        workflow.add_conditional_edges(
            "run_guardrails",
            self._should_block,
            {
                "block": "handle_violation",
                "proceed": "route_model",
            },
        )

        workflow.add_edge("route_model", "generate_response")
        workflow.add_edge("generate_response", "store_and_audit")
        workflow.add_edge("handle_violation", "store_and_audit")
        workflow.add_edge("store_and_audit", END)

        return workflow.compile()

    # ---------------------------------------------------------------------------
    # Nodes
    # ---------------------------------------------------------------------------
    def _node_load_history(self, state: AgentState) -> dict:
        """Load conversation history from Supabase."""
        history = self.supabase.get_conversation_history(
            user_id=state["user_id"],
            session_id=state["session_id"],
            limit=20,
        )

        messages = []
        for turn in history:
            if turn["role"] == "user":
                messages.append(HumanMessage(content=turn["content"]))
            elif turn["role"] == "assistant":
                messages.append(AIMessage(content=turn["content"]))

        # Add current user message
        messages.append(HumanMessage(content=state["user_message"]))

        return {"messages": messages}

    def _node_run_guardrails(self, state: AgentState) -> dict:
        """Run all guardrail checks on the user message."""
        checks = self.guardrails.run_all_checks(state["user_message"])

        warnings = checks["warnings"]
        has_violation = checks["has_violations"]
        violation_response = None

        if has_violation:
            pc = checks["product_check"]
            parts = [f"WARNING: {pc.warning}"]
            if pc.suggested_alternative:
                parts.append(
                    f"Suggested alternative: {pc.suggested_alternative}"
                )
            parts.append(
                "This quote request has been BLOCKED due to product constraint violation. "
                "Please verify the correct product for your application."
            )
            violation_response = "\n\n".join(parts)

        # Also build context about pricing/discount for the LLM
        pricing_context = ""
        if checks["pricing_check"].is_pricing_request:
            pc = checks["pricing_check"]
            pricing_context += (
                f"\n[SYSTEM: Pricing request detected. Route to {pc.authority}. "
                "Do NOT generate any price numbers.]"
            )
        if checks["discount_check"].discount_requested:
            dc = checks["discount_check"]
            pricing_context += (
                f"\n[SYSTEM: Discount request. {dc.reason} "
                "Do NOT approve any discount.]"
            )

        # Append pricing context to messages if present
        updated_messages = list(state.get("messages", []))
        if pricing_context:
            updated_messages.append(SystemMessage(content=pricing_context))

        return {
            "guardrail_warnings": warnings,
            "has_violation": has_violation,
            "violation_response": violation_response,
            "messages": updated_messages,
        }

    def _should_block(self, state: AgentState) -> str:
        """Conditional edge: block on product violation, proceed otherwise."""
        if state.get("has_violation"):
            return "block"
        return "proceed"

    def _node_route_model(self, state: AgentState) -> dict:
        """Route to appropriate Claude model based on task complexity."""
        routing = self.router.classify(state["user_message"])

        # Log routing decision
        self.audit.log_model_route(
            user_id=state["user_id"],
            session_id=state["session_id"],
            input_text=state["user_message"],
            model_used=routing.model_id,
            tier=routing.tier.value,
            reason=routing.reason,
        )

        return {
            "model_tier": routing.tier.value,
            "model_id": routing.model_id,
            "routing_reason": routing.reason,
        }

    def _node_generate_response(self, state: AgentState) -> dict:
        """Generate response using the routed model via AWS Bedrock."""
        start = time.time()

        routing = self.router.classify(state["user_message"])

        # Convert LangChain messages to Bedrock API format
        api_messages = []
        for msg in state.get("messages", []):
            if isinstance(msg, HumanMessage):
                api_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                api_messages.append({"role": "assistant", "content": msg.content})
            # SystemMessages are folded into the system prompt

        # Build enhanced system prompt with any guardrail context
        system_prompt = GENOTEK_SYSTEM_PROMPT
        for msg in state.get("messages", []):
            if isinstance(msg, SystemMessage):
                system_prompt += f"\n\n{msg.content}"

        llm_response = self.router.invoke(
            messages=api_messages,
            system_prompt=system_prompt,
            routing=routing,
        )

        latency = int((time.time() - start) * 1000)

        return {
            "response": llm_response.content,
            "model_used": llm_response.model_id,
            "tokens_input": llm_response.tokens_input,
            "tokens_output": llm_response.tokens_output,
            "cost_estimate": llm_response.cost_estimate,
            "latency_ms": latency,
        }

    def _node_handle_violation(self, state: AgentState) -> dict:
        """Handle product constraint violations -- return warning, no LLM call."""
        response = state.get("violation_response", "Product constraint violation detected.")

        # Log the violation
        pc = self.guardrails.check_product_constraints(state["user_message"])
        self.audit.log_product_violation(
            user_id=state["user_id"],
            username=state.get("username"),
            session_id=state["session_id"],
            input_text=state["user_message"],
            warning=pc.warning,
            product_code=pc.product_code,
            suggested_alternative=pc.suggested_alternative,
        )

        return {
            "response": response,
            "model_used": "guardrails-only",
            "tokens_input": 0,
            "tokens_output": 0,
            "cost_estimate": 0.0,
            "latency_ms": 0,
        }

    def _node_store_and_audit(self, state: AgentState) -> dict:
        """Store conversation turns and create audit log entry."""
        # Store user turn
        self.supabase.store_conversation_turn(
            user_id=state["user_id"],
            username=state.get("username"),
            session_id=state["session_id"],
            role="user",
            content=state["user_message"],
        )

        # Store assistant turn
        self.supabase.store_conversation_turn(
            user_id=state["user_id"],
            username=state.get("username"),
            session_id=state["session_id"],
            role="assistant",
            content=state.get("response", ""),
            model_used=state.get("model_used"),
            tokens_input=state.get("tokens_input", 0),
            tokens_output=state.get("tokens_output", 0),
            cost_estimate=state.get("cost_estimate", 0.0),
        )

        # Audit log
        warnings = state.get("guardrail_warnings", [])

        # Log pricing escalation if detected
        checks = self.guardrails.run_all_checks(state["user_message"])
        if checks["pricing_check"].is_pricing_request:
            self.audit.log_pricing_escalation(
                user_id=state["user_id"],
                username=state.get("username"),
                session_id=state["session_id"],
                input_text=state["user_message"],
                authority=checks["pricing_check"].authority or "Unknown",
                region=checks["pricing_check"].region,
                reason=f"Pricing request routed to {checks['pricing_check'].authority}",
            )

        if checks["discount_check"].discount_requested:
            self.audit.log_discount_escalation(
                user_id=state["user_id"],
                username=state.get("username"),
                session_id=state["session_id"],
                input_text=state["user_message"],
                authority=checks["discount_check"].authority or "Bijoy",
                reason=checks["discount_check"].reason,
            )

        # Main message audit
        self.audit.log_message(
            user_id=state["user_id"],
            username=state.get("username"),
            session_id=state["session_id"],
            input_text=state["user_message"],
            output_text=state.get("response", ""),
            model_used=state.get("model_used", "unknown"),
            latency_ms=state.get("latency_ms", 0),
            warnings=warnings,
        )

        return {}

    # ---------------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------------
    def process_message(
        self,
        user_message: str,
        user_id: int,
        username: Optional[str],
        session_id: str,
    ) -> dict:
        """
        Process a user message through the full workflow.
        Returns dict with 'response', 'model_used', 'warnings', etc.
        """
        initial_state: AgentState = {
            "user_message": user_message,
            "user_id": user_id,
            "username": username,
            "session_id": session_id,
            "messages": [],
            "guardrail_warnings": [],
            "has_violation": False,
            "violation_response": None,
            "model_tier": None,
            "model_id": None,
            "routing_reason": None,
            "response": None,
            "model_used": None,
            "tokens_input": 0,
            "tokens_output": 0,
            "cost_estimate": 0.0,
            "latency_ms": 0,
        }

        try:
            result = self.graph.invoke(initial_state)
            return {
                "response": result.get("response", "I encountered an issue processing your request."),
                "model_used": result.get("model_used", "unknown"),
                "model_tier": result.get("model_tier"),
                "warnings": result.get("guardrail_warnings", []),
                "tokens_input": result.get("tokens_input", 0),
                "tokens_output": result.get("tokens_output", 0),
                "cost_estimate": result.get("cost_estimate", 0.0),
                "latency_ms": result.get("latency_ms", 0),
            }
        except Exception as e:
            logger.error("Graph execution failed: %s", e, exc_info=True)
            self.audit.log_error(
                user_id=user_id,
                session_id=session_id,
                input_text=user_message,
                error=str(e),
            )
            return {
                "response": (
                    "I encountered an error processing your request. "
                    "This has been logged for review. Please try again or "
                    "escalate to the team directly."
                ),
                "model_used": "error",
                "warnings": [str(e)],
                "tokens_input": 0,
                "tokens_output": 0,
                "cost_estimate": 0.0,
                "latency_ms": 0,
            }
