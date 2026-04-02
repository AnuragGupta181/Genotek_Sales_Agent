"""
Tests for the guardrails module.
Covers: product constraints (VT-1), pricing authority (VT-2), discount escalation (VT-3).
"""

import pytest
from unittest.mock import MagicMock, patch
from bot.guardrails import Guardrails, ConstraintCheckResult, PricingCheckResult


# ---------------------------------------------------------------------------
# Fixtures: mock Supabase with product data
# ---------------------------------------------------------------------------
MOCK_PRODUCTS = [
    {
        "product_code": "WTZ-1800",
        "product_name": "WTZ-1800 Expansion Joint Cover",
        "product_family": "WTZ",
        "description": "Wall/ceiling expansion joint cover for above-waterline applications",
        "application_constraints": {
            "environment": "above-waterline",
            "prohibited_environments": [
                "submerged", "underwater", "below-waterline", "pool-submerged"
            ],
            "max_movement_mm": 50,
            "fire_rated": False,
        },
        "supplier_name": "Ankara Factory",
        "regions": ["UAE", "KSA", "India", "SEA"],
        "is_active": True,
    },
    {
        "product_code": "WTZ-2400",
        "product_name": "WTZ-2400 Expansion Joint Cover (Waterproof)",
        "product_family": "WTZ",
        "description": "Expansion joint cover rated for submerged and below-waterline",
        "application_constraints": {
            "environment": "all-weather",
            "submersible": True,
            "waterproof": True,
            "max_movement_mm": 75,
            "fire_rated": False,
        },
        "supplier_name": "Ankara Factory",
        "regions": ["UAE", "KSA", "India", "SEA"],
        "is_active": True,
    },
    {
        "product_code": "WTZ-1200",
        "product_name": "WTZ-1200 Standard Expansion Joint Cover",
        "product_family": "WTZ",
        "description": "Standard expansion joint cover",
        "application_constraints": {
            "environment": "above-waterline",
            "prohibited_environments": [
                "submerged", "underwater", "below-waterline"
            ],
            "max_movement_mm": 30,
            "fire_rated": False,
        },
        "supplier_name": "Ankara Factory",
        "regions": ["UAE", "KSA", "India", "SEA"],
        "is_active": True,
    },
    {
        "product_code": "WTZ-3000",
        "product_name": "WTZ-3000 Heavy Duty Floor Joint",
        "product_family": "WTZ",
        "description": "Heavy-duty floor expansion joint",
        "application_constraints": {
            "environment": "floor",
            "traffic_rated": True,
            "prohibited_environments": ["wall-mount", "ceiling"],
        },
        "supplier_name": "Ankara Factory",
        "regions": ["UAE", "KSA", "India", "SEA"],
        "is_active": True,
    },
]


@pytest.fixture
def mock_supabase():
    """Create a mock SupabaseManager with pre-loaded product data."""
    sb = MagicMock()
    sb.get_all_products.return_value = MOCK_PRODUCTS
    sb.get_product.side_effect = lambda code: next(
        (p for p in MOCK_PRODUCTS if p["product_code"] == code.upper()), None
    )
    return sb


@pytest.fixture
def guardrails(mock_supabase):
    """Create Guardrails instance with mock data."""
    return Guardrails(mock_supabase)


# ===========================================================================
# VT-1: Product Constraint Guardrail
# ===========================================================================
class TestProductConstraints:
    """Tests per SPEC.md VT-1: Product constraint enforcement."""

    def test_wtz1800_submerged_pool_joint(self, guardrails):
        """SPEC VT-1: WTZ-1800 for submerged pool joint must be flagged."""
        result = guardrails.check_product_constraints(
            "Quote WTZ-1800 for submerged pool joint"
        )
        assert result.violation is True
        assert "above-waterline" in result.warning
        assert result.suggested_alternative is not None
        assert result.action_type == "PRODUCT_CONSTRAINT_VIOLATION"

    def test_wtz1800_underwater(self, guardrails):
        """WTZ-1800 + underwater context must be flagged."""
        result = guardrails.check_product_constraints(
            "Need WTZ-1800 for underwater application"
        )
        assert result.violation is True
        assert result.product_code == "WTZ-1800"

    def test_wtz1800_swimming_pool(self, guardrails):
        """WTZ-1800 + swimming pool context must be flagged."""
        result = guardrails.check_product_constraints(
            "Can we use WTZ-1800 for the swimming pool expansion joints?"
        )
        assert result.violation is True

    def test_wtz1800_normal_use_ok(self, guardrails):
        """WTZ-1800 in normal above-waterline context should pass."""
        result = guardrails.check_product_constraints(
            "Quote WTZ-1800 for wall expansion joint in Dubai office"
        )
        assert result.violation is False

    def test_wtz2400_submerged_ok(self, guardrails):
        """WTZ-2400 (waterproof) for submerged use should pass."""
        result = guardrails.check_product_constraints(
            "Quote WTZ-2400 for submerged pool joint"
        )
        assert result.violation is False

    def test_wtz1200_underwater_flagged(self, guardrails):
        """WTZ-1200 also cannot be used underwater."""
        result = guardrails.check_product_constraints(
            "I need WTZ-1200 for an underwater fountain joint"
        )
        assert result.violation is True

    def test_no_product_code_no_violation(self, guardrails):
        """Messages without product codes should not trigger violations."""
        result = guardrails.check_product_constraints(
            "What expansion joints do you have for pools?"
        )
        assert result.violation is False

    def test_suggested_alternative_is_wtz2400(self, guardrails):
        """When WTZ-1800 is blocked for submerged, WTZ-2400 should be suggested."""
        result = guardrails.check_product_constraints(
            "Quote WTZ-1800 for submerged pool joint"
        )
        assert result.suggested_alternative is not None
        assert "WTZ-2400" in result.suggested_alternative


# ===========================================================================
# VT-2: Pricing Authority Routing
# ===========================================================================
class TestPricingRouting:
    """Tests per SPEC.md VT-2: Pricing requests never generate prices."""

    def test_pricing_request_detected(self, guardrails):
        """Pricing request must be detected."""
        result = guardrails.check_pricing_request(
            "What's the price for WTZ-1200 for UAE?"
        )
        assert result.is_pricing_request is True
        assert result.price_generated is False  # NEVER

    def test_uae_routes_to_shylesh(self, guardrails):
        """UAE pricing routes to Shylesh."""
        result = guardrails.check_pricing_request(
            "Need pricing for UAE expansion joint project"
        )
        assert result.is_pricing_request is True
        assert result.authority == "Shylesh"

    def test_ksa_routes_to_bijoy(self, guardrails):
        """KSA pricing routes to Bijoy."""
        result = guardrails.check_pricing_request(
            "What's the price for KSA project?"
        )
        assert result.is_pricing_request is True
        assert result.authority == "Bijoy"

    def test_india_routes_to_niranjan(self, guardrails):
        """India pricing routes to Niranjan."""
        result = guardrails.check_pricing_request(
            "Need pricing for India Mumbai project"
        )
        assert result.is_pricing_request is True
        assert result.authority == "Niranjan"

    def test_unknown_region_routes_to_bijoy(self, guardrails):
        """Unknown region pricing routes to Bijoy (strategic)."""
        result = guardrails.check_pricing_request(
            "What's the cost for this project?"
        )
        assert result.is_pricing_request is True
        assert result.authority == "Bijoy"

    def test_non_pricing_not_flagged(self, guardrails):
        """Non-pricing messages should not be flagged."""
        result = guardrails.check_pricing_request(
            "Tell me about the WTZ product line"
        )
        assert result.is_pricing_request is False


# ===========================================================================
# VT-3: Discount Escalation
# ===========================================================================
class TestDiscountEscalation:
    """Tests per SPEC.md VT-3: Discount requests properly escalated."""

    def test_20pct_discount_to_bijoy(self, guardrails):
        """20% discount must route to Bijoy (>15% threshold)."""
        result = guardrails.check_discount_request(
            "Can we offer 20% discount on this order?"
        )
        assert result.requires_escalation is True
        assert result.authority == "Bijoy"
        assert result.discount_approved is False  # NEVER approve

    def test_10pct_discount_needs_approval(self, guardrails):
        """10% discount still requires approval (just not always Bijoy)."""
        result = guardrails.check_discount_request(
            "Client wants 10% discount for UAE project"
        )
        assert result.requires_escalation is True
        assert result.discount_approved is False

    def test_unspecified_discount_to_bijoy(self, guardrails):
        """Discount without percentage routes to Bijoy conservatively."""
        result = guardrails.check_discount_request(
            "Client is asking for a discount"
        )
        assert result.requires_escalation is True
        assert result.authority == "Bijoy"

    def test_no_discount_not_flagged(self, guardrails):
        """Messages without discount requests should not be flagged."""
        result = guardrails.check_discount_request(
            "Please send the standard quotation"
        )
        assert result.discount_requested is False


# ===========================================================================
# run_all_checks integration
# ===========================================================================
class TestRunAllChecks:
    """Tests for the combined guardrail check."""

    def test_violation_flagged_in_combined(self, guardrails):
        """Product violation should appear in combined warnings."""
        result = guardrails.run_all_checks(
            "Quote WTZ-1800 for submerged pool joint"
        )
        assert result["has_violations"] is True
        assert len(result["warnings"]) >= 1
        assert any("CONSTRAINT VIOLATION" in w for w in result["warnings"])

    def test_pricing_flagged_in_combined(self, guardrails):
        """Pricing request should appear in combined warnings."""
        result = guardrails.run_all_checks(
            "What's the price for WTZ-1200 for UAE project?"
        )
        assert any("Pricing request" in w for w in result["warnings"])

    def test_clean_message_no_warnings(self, guardrails):
        """Clean message should have no warnings."""
        result = guardrails.run_all_checks("Hello, how are you?")
        assert result["has_violations"] is False
        assert len(result["warnings"]) == 0
