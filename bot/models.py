"""
Model routing module for Genotek Sales Support Bot.
Routes tasks to appropriate Claude models via AWS Bedrock (primary) or direct API (fallback).
Implements the 80/15/5 split: Haiku / Sonnet / Opus.
"""

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import boto3

# ---------------------------------------------------------------------------
# Uncomment for direct Anthropic API usage (set USE_BEDROCK=false in .env)
# ---------------------------------------------------------------------------
# import anthropic

from bot.config import BEDROCK_MODELS, Config

logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    """Model tiers mapped to task complexity."""
    HAIKU = "haiku"    # ~80% of tasks: triage, classification, reminders
    SONNET = "sonnet"  # ~15% of tasks: quote drafting, routing decisions
    OPUS = "opus"      # ~5% of tasks: complex pricing, multi-region exceptions


@dataclass
class RoutingResult:
    """Result of model routing classification."""
    tier: ModelTier
    model_id: str
    reason: str


@dataclass
class LLMResponse:
    """Structured response from the LLM."""
    content: str
    model_id: str
    tier: ModelTier
    tokens_input: int
    tokens_output: int
    cost_estimate: float


# Keywords/patterns for routing classification
_COMPLEX_PATTERNS = [
    r"multi[- ]?region",
    r"pricing\s+exception",
    r"volume\s+discount\s+tier",
    r"complex\s+pricing",
    r"strategic\s+analysis",
    r"cross[- ]?border",
    r"exception\s+handling",
    r"competitive\s+analysis",
]

_MEDIUM_PATTERNS = [
    r"draft\s+(a\s+)?quote",
    r"compile\s+quote",
    r"quotation\s+for",
    r"prepare\s+(a\s+)?quote",
    r"route\s+pricing",
    r"pricing\s+request",
    r"follow[- ]?up\s+template",
    r"email\s+draft",
    r"submittal\s+package",
    r"product\s+recommendation",
    r"supplier\s+status\s+report",
    r"deal\s+analysis",
    r"(?i)WTZ-\d+|EJ-\w+|FB-\w+",  # Product code mentions (case-insensitive)
]


class ModelRouter:
    """Classifies task complexity and routes to the appropriate Claude model."""

    def __init__(self, config: Config):
        self.config = config

        if config.use_bedrock:
            self.bedrock_client = boto3.client(
                "bedrock-runtime",
                region_name=config.aws_region,
                aws_access_key_id=config.aws_access_key_id,
                aws_secret_access_key=config.aws_secret_access_key,
            )
        # ------------------------------------------------------------------
        # Direct Anthropic API client (uncomment if USE_BEDROCK=false)
        # ------------------------------------------------------------------
        # else:
        #     self.anthropic_client = anthropic.Anthropic(
        #         api_key=config.anthropic_api_key
        #     )

    def classify(self, message: str) -> RoutingResult:
        """Classify a message to determine which model tier to use."""
        lower_msg = message.lower().strip()

        # Check for complex patterns first (Opus -- ~5%)
        for pattern in _COMPLEX_PATTERNS:
            if re.search(pattern, lower_msg):
                model_cfg = BEDROCK_MODELS["opus"]
                return RoutingResult(
                    tier=ModelTier.OPUS,
                    model_id=model_cfg.model_id,
                    reason=f"Complex task detected (pattern: {pattern})",
                )

        # Check for medium patterns (Sonnet -- ~15%)
        for pattern in _MEDIUM_PATTERNS:
            if re.search(pattern, lower_msg):
                model_cfg = BEDROCK_MODELS["sonnet"]
                return RoutingResult(
                    tier=ModelTier.SONNET,
                    model_id=model_cfg.model_id,
                    reason=f"Medium complexity task (pattern: {pattern})",
                )

        # Default to Haiku for everything else (~80%)
        model_cfg = BEDROCK_MODELS["haiku"]
        return RoutingResult(
            tier=ModelTier.HAIKU,
            model_id=model_cfg.model_id,
            reason="Simple task -- routed to fastest/cheapest model",
        )

    def invoke(
        self,
        messages: list[dict],
        system_prompt: str,
        routing: RoutingResult,
    ) -> LLMResponse:
        """Invoke the selected model via AWS Bedrock."""
        model_cfg = BEDROCK_MODELS[routing.tier.value]

        if self.config.use_bedrock:
            return self._invoke_bedrock(messages, system_prompt, model_cfg, routing)
        else:
            return self._invoke_direct(messages, system_prompt, model_cfg, routing)

    def _invoke_bedrock(
        self,
        messages: list[dict],
        system_prompt: str,
        model_cfg,
        routing: RoutingResult,
    ) -> LLMResponse:
        """Call model via AWS Bedrock."""
        model_id_lower = model_cfg.model_id.lower()
        
        # Check if using Nova models
        if "nova" in model_id_lower:
            # Nova format
            body = self._build_nova_body(messages, system_prompt, model_cfg)
        elif "titan" in model_id_lower:
            # Titan format
            prompt = self._build_titan_prompt(messages, system_prompt)
            body = {
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": model_cfg.max_tokens,
                    "temperature": model_cfg.temperature,
                    "topP": 0.9,
                }
            }
        else:
            # Claude format
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": model_cfg.max_tokens,
                "temperature": model_cfg.temperature,
                "system": system_prompt,
                "messages": messages,
            }

        response = self.bedrock_client.invoke_model(
            modelId=model_cfg.model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )

        result = json.loads(response["body"].read())

        # Handle different response formats
        if "nova" in model_id_lower:
            # Nova response format
            content = ""
            if "output" in result and "message" in result["output"]:
                content = result["output"]["message"].get("content", [{}])[0].get("text", "")
            tokens_in = result.get("usage", {}).get("inputTokens", 0)
            tokens_out = result.get("usage", {}).get("outputTokens", 0)
        elif "titan" in model_id_lower:
            # Titan response format
            content = ""
            if "results" in result and len(result["results"]) > 0:
                content = result["results"][0].get("outputText", "")
            tokens_in = result.get("inputTextTokenCount", 0)
            tokens_out = result.get("results", [{}])[0].get("tokenCount", 0) if "results" in result else 0
        else:
            # Claude response format
            content = ""
            for block in result.get("content", []):
                if block.get("type") == "text":
                    content += block["text"]
            tokens_in = result.get("usage", {}).get("input_tokens", 0)
            tokens_out = result.get("usage", {}).get("output_tokens", 0)

        cost = (
            (tokens_in / 1_000_000) * model_cfg.cost_per_1m_input
            + (tokens_out / 1_000_000) * model_cfg.cost_per_1m_output
        )

        return LLMResponse(
            content=content,
            model_id=model_cfg.model_id,
            tier=routing.tier,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            cost_estimate=cost,
        )

    def _build_nova_body(self, messages: list[dict], system_prompt: str, model_cfg) -> dict:
        """Build request body for Amazon Nova models."""
        # Convert messages to Nova format
        nova_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # Handle content that might be a list
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                content = " ".join(text_parts)
            
            nova_messages.append({
                "role": role,
                "content": [{"text": content}]
            })
        
        body = {
            "messages": nova_messages,
            "inferenceConfig": {
                "max_new_tokens": model_cfg.max_tokens,
                "temperature": model_cfg.temperature,
                "top_p": 0.9,
            }
        }
        
        if system_prompt:
            body["system"] = [{"text": system_prompt}]
        
        return body

    def _build_titan_prompt(self, messages: list[dict], system_prompt: str) -> str:
        """Build a prompt string for Titan models from messages."""
        prompt_parts = []
        if system_prompt:
            prompt_parts.append(f"System: {system_prompt}\n")
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                # Handle content blocks
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                content = " ".join(text_parts)
            prompt_parts.append(f"{role.capitalize()}: {content}\n")
        
        prompt_parts.append("Assistant: ")
        return "\n".join(prompt_parts)

    def _invoke_direct(
        self,
        messages: list[dict],
        system_prompt: str,
        model_cfg,
        routing: RoutingResult,
    ) -> LLMResponse:
        """
        Call Claude via direct Anthropic API.
        Currently a stub -- uncomment the anthropic import and client init above.
        """
        # ------------------------------------------------------------------
        # DIRECT ANTHROPIC API IMPLEMENTATION
        # Uncomment this block and the anthropic import to use direct API.
        # ------------------------------------------------------------------
        # direct_cfg = DIRECT_MODELS[routing.tier.value]
        # response = self.anthropic_client.messages.create(
        #     model=direct_cfg["model"],
        #     max_tokens=direct_cfg["max_tokens"],
        #     temperature=direct_cfg["temperature"],
        #     system=system_prompt,
        #     messages=messages,
        # )
        #
        # content = ""
        # for block in response.content:
        #     if block.type == "text":
        #         content += block.text
        #
        # tokens_in = response.usage.input_tokens
        # tokens_out = response.usage.output_tokens
        # cost = (
        #     (tokens_in / 1_000_000) * model_cfg.cost_per_1m_input
        #     + (tokens_out / 1_000_000) * model_cfg.cost_per_1m_output
        # )
        #
        # return LLMResponse(
        #     content=content,
        #     model_id=direct_cfg["model"],
        #     tier=routing.tier,
        #     tokens_input=tokens_in,
        #     tokens_output=tokens_out,
        #     cost_estimate=cost,
        # )
        # ------------------------------------------------------------------

        raise NotImplementedError(
            "Direct Anthropic API not enabled. Set USE_BEDROCK=true or uncomment "
            "the direct API code in models.py."
        )
