"""
Tests for the model routing module.
Covers: SPEC.md VT-6 -- Model routing correctness.
"""

import pytest
from bot.models import ModelRouter, ModelTier, RoutingResult
from bot.config import Config, BEDROCK_MODELS
from unittest.mock import MagicMock


@pytest.fixture
def router():
    """Create a ModelRouter with mock config (no actual AWS connection)."""
    config = MagicMock(spec=Config)
    config.use_bedrock = True
    config.aws_region = "us-east-1"
    config.aws_access_key_id = "test"
    config.aws_secret_access_key = "test"

    # Patch boto3 so it doesn't actually connect
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("boto3.client", lambda *a, **kw: MagicMock())
        return ModelRouter(config)


# ===========================================================================
# VT-6: Model Routing
# ===========================================================================
class TestModelRouting:
    """Tests per SPEC.md VT-6: Correct model selection per task complexity."""

    def test_simple_greeting_routes_to_haiku(self, router):
        """Simple greeting -> Haiku (~80% of tasks)."""
        result = router.classify("Hello")
        assert result.tier == ModelTier.HAIKU
        assert "haiku" in result.model_id.lower()

    def test_general_question_routes_to_haiku(self, router):
        """General question -> Haiku."""
        result = router.classify("What products do you have?")
        assert result.tier == ModelTier.HAIKU

    def test_status_check_routes_to_haiku(self, router):
        """Simple status check -> Haiku."""
        result = router.classify("How are you doing?")
        assert result.tier == ModelTier.HAIKU

    def test_quote_draft_routes_to_sonnet(self, router):
        """Quote drafting request -> Sonnet (~15% of tasks)."""
        result = router.classify("Draft a quote for UAE expansion joint project")
        assert result.tier == ModelTier.SONNET
        assert "sonnet" in result.model_id.lower()

    def test_pricing_request_routes_to_sonnet(self, router):
        """Pricing routing request -> Sonnet."""
        result = router.classify("Route pricing request for this KSA project")
        assert result.tier == ModelTier.SONNET

    def test_product_code_routes_to_sonnet(self, router):
        """Product code mention -> Sonnet."""
        result = router.classify("Tell me about WTZ-1800 specifications")
        assert result.tier == ModelTier.SONNET

    def test_follow_up_template_routes_to_sonnet(self, router):
        """Follow-up template request -> Sonnet."""
        result = router.classify("Create a follow-up template for the client")
        assert result.tier == ModelTier.SONNET

    def test_complex_pricing_routes_to_opus(self, router):
        """Complex pricing exception -> Opus (~5% of tasks)."""
        result = router.classify(
            "Analyze multi-region pricing exception with volume discount tiers"
        )
        assert result.tier == ModelTier.OPUS
        assert "opus" in result.model_id.lower()

    def test_strategic_analysis_routes_to_opus(self, router):
        """Strategic analysis -> Opus."""
        result = router.classify("Provide strategic analysis of cross-border deal")
        assert result.tier == ModelTier.OPUS

    def test_exception_handling_routes_to_opus(self, router):
        """Exception handling request -> Opus."""
        result = router.classify(
            "We need exception handling for this complex pricing scenario"
        )
        assert result.tier == ModelTier.OPUS


class TestRoutingResult:
    """Test RoutingResult structure."""

    def test_routing_result_has_required_fields(self, router):
        """Every routing result must have tier, model_id, and reason."""
        result = router.classify("test message")
        assert result.tier is not None
        assert result.model_id is not None
        assert result.reason is not None
        assert len(result.reason) > 0

    def test_all_tiers_map_to_valid_models(self):
        """Every tier must map to a model in BEDROCK_MODELS."""
        for tier in ModelTier:
            assert tier.value in BEDROCK_MODELS
            model_cfg = BEDROCK_MODELS[tier.value]
            assert model_cfg.model_id is not None
            assert model_cfg.cost_per_1m_input >= 0
            assert model_cfg.cost_per_1m_output >= 0
