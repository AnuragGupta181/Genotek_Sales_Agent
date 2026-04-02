"""
Product guardrails module for Genotek Sales Support Bot.
Enforces product application constraints and pricing authority boundaries.
Per SPEC.md: CR-4, FM-2, FM-3.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from bot.supabase_client import SupabaseManager

logger = logging.getLogger(__name__)


@dataclass
class ConstraintCheckResult:
    """Result of a product constraint check."""
    violation: bool = False
    warning: str = ""
    suggested_alternative: Optional[str] = None
    product_code: Optional[str] = None
    action_type: str = "PRODUCT_CHECK"


@dataclass
class PricingCheckResult:
    """Result of a pricing authority check."""
    is_pricing_request: bool = False
    authority: Optional[str] = None
    region: Optional[str] = None
    reason: str = ""
    price_generated: bool = False  # Must ALWAYS be False per SPEC CR-1
    requires_escalation: bool = False
    discount_requested: bool = False
    discount_approved: bool = False  # Must ALWAYS be False per SPEC CR-2


# Patterns for detecting submerged/underwater contexts
_SUBMERGED_PATTERNS = [
    r"submerge[ds]?",
    r"under\s*water",
    r"below[- ]?water[- ]?line",
    r"pool\s+joint",
    r"swimming\s+pool",
    r"water\s*proof\s+joint",
    r"fountain",
    r"aquatic",
    r"immerse[ds]?",
    r"water\s*tank",
]

# Patterns for detecting pricing requests
_PRICING_PATTERNS = [
    r"(?:what(?:'s| is) the )?price",
    r"how much",
    r"cost(?:ing)?",
    r"quot(?:e|ation)\s+(?:for|price)",
    r"pricing",
    r"rate\s+for",
    r"per\s+(?:meter|lm|sqm|unit)",
    r"budget\s+estimate",
]

# Patterns for detecting discount requests
_DISCOUNT_PATTERNS = [
    r"discount",
    r"price\s+reduction",
    r"lower\s+(?:the\s+)?price",
    r"better\s+(?:rate|price|deal)",
    r"special\s+(?:rate|price|offer)",
    r"bulk\s+(?:rate|pricing|discount)",
    r"negotiat",
    r"(\d+)\s*%\s*(?:off|discount|reduction)",
]

# Region detection patterns
_REGION_PATTERNS = {
    "UAE": [r"\bUAE\b", r"\bDubai\b", r"\bAbu\s*Dhabi\b", r"\bSharjah\b", r"\bAED\b", r"United Arab Emirates"],
    "KSA": [r"\bKSA\b", r"\bSaudi\b", r"\bRiyadh\b", r"\bJeddah\b", r"\bSAR\b", r"Saudi Arabia"],
    "India": [r"\bIndia\b", r"\bMumbai\b", r"\bDelhi\b", r"\bBangalore\b", r"\bPidilite\b", r"\bINR\b"],
    "SEA": [r"\bSingapore\b", r"\bThailand\b", r"\bMalaysia\b", r"\bSGD\b", r"\bSEA\b", r"Southeast Asia"],
    "Turkey": [r"\bTurkey\b", r"\bAnkara\b", r"\bTurkish\b", r"\bTRY\b"],
    "NZ": [r"\bNew Zealand\b", r"\bNZ\b", r"\bNZD\b", r"\bAuckland\b"],
}

# Product code pattern
_PRODUCT_CODE_RE = re.compile(r"\b(WTZ-\d{3,4}|EJ-[A-Z]{2}\d{3}|FB-[A-Z0-9]{3,6})\b", re.IGNORECASE)


class Guardrails:
    """Enforces product constraints and pricing authority rules."""

    def __init__(self, supabase: SupabaseManager):
        self.supabase = supabase
        # Cache products on init for fast constraint checking
        self._products_cache: dict[str, dict] = {}
        self._load_products_cache()

    def _load_products_cache(self):
        """Load all products into memory for fast lookups."""
        try:
            products = self.supabase.get_all_products()
            for p in products:
                self._products_cache[p["product_code"].upper()] = p
            logger.info("Loaded %d products into guardrails cache", len(self._products_cache))
        except Exception as e:
            logger.error("Failed to load products cache: %s", e)

    def extract_product_codes(self, message: str) -> list[str]:
        """Extract product codes from a message."""
        return [m.group(1).upper() for m in _PRODUCT_CODE_RE.finditer(message)]

    def check_product_constraints(self, message: str) -> ConstraintCheckResult:
        """
        Check if any product mentioned in the message violates application constraints.
        Per SPEC.md CR-4 and FM-2.
        """
        product_codes = self.extract_product_codes(message)
        if not product_codes:
            return ConstraintCheckResult()

        lower_msg = message.lower()

        for code in product_codes:
            product = self._products_cache.get(code)
            if not product:
                # Try fetching from DB if not in cache
                product = self.supabase.get_product(code)
                if product:
                    self._products_cache[code] = product

            if not product:
                continue

            constraints = product.get("application_constraints", {})
            prohibited = constraints.get("prohibited_environments", [])

            # Check if message context matches any prohibited environment
            for env in prohibited:
                env_patterns = {
                    "submerged": _SUBMERGED_PATTERNS,
                    "underwater": _SUBMERGED_PATTERNS,
                    "below-waterline": _SUBMERGED_PATTERNS,
                    "pool-submerged": _SUBMERGED_PATTERNS,
                    "exterior-exposed": [r"exterior", r"outdoor", r"weather[- ]?exposed"],
                    "wall-mount": [r"wall\s*mount", r"wall\s+install"],
                    "ceiling": [r"ceiling", r"overhead"],
                }

                patterns = env_patterns.get(env, [re.escape(env)])
                for pattern in patterns:
                    if re.search(pattern, lower_msg, re.IGNORECASE):
                        # Find alternative product
                        alternative = self._find_alternative(code, env)
                        env_label = constraints.get("environment", "restricted")

                        return ConstraintCheckResult(
                            violation=True,
                            warning=(
                                f"PRODUCT CONSTRAINT VIOLATION: {code} is rated for "
                                f"{env_label} applications only. It cannot be used in "
                                f"{env} environments."
                            ),
                            suggested_alternative=alternative,
                            product_code=code,
                            action_type="PRODUCT_CONSTRAINT_VIOLATION",
                        )

        return ConstraintCheckResult(product_code=product_codes[0] if product_codes else None)

    def _find_alternative(self, current_code: str, required_env: str) -> Optional[str]:
        """Find an alternative product suitable for the required environment."""
        current = self._products_cache.get(current_code, {})
        current_family = current.get("product_family", "")

        for code, product in self._products_cache.items():
            if code == current_code:
                continue
            if product.get("product_family") != current_family:
                continue

            constraints = product.get("application_constraints", {})

            # Check if this product allows the required environment
            prohibited = constraints.get("prohibited_environments", [])
            if required_env not in prohibited:
                submersible = constraints.get("submersible", False)
                if required_env in ("submerged", "underwater", "below-waterline", "pool-submerged"):
                    if submersible or constraints.get("waterproof", False):
                        return f"{code} ({product.get('product_name', '')})"
                else:
                    return f"{code} ({product.get('product_name', '')})"

        return None

    def check_pricing_request(self, message: str) -> PricingCheckResult:
        """
        Detect pricing requests and route to correct authority.
        Per SPEC.md CR-1 and FM-3.
        """
        lower_msg = message.lower()
        result = PricingCheckResult()

        # Check for pricing patterns
        for pattern in _PRICING_PATTERNS:
            if re.search(pattern, lower_msg):
                result.is_pricing_request = True
                break

        if not result.is_pricing_request:
            return result

        # Detect region
        result.region = self._detect_region(message)

        # Route to authority based on region
        result.authority = self._route_pricing_authority(result.region, message)
        result.price_generated = False  # NEVER generate price (CR-1)

        return result

    def check_discount_request(self, message: str) -> PricingCheckResult:
        """
        Detect discount requests and enforce escalation rules.
        Per SPEC.md CR-2.
        """
        lower_msg = message.lower()
        result = PricingCheckResult()

        for pattern in _DISCOUNT_PATTERNS:
            match = re.search(pattern, lower_msg)
            if match:
                result.discount_requested = True
                result.is_pricing_request = True

                # Extract discount percentage if mentioned
                pct_match = re.search(r"(\d+)\s*%", lower_msg)
                if pct_match:
                    pct = int(pct_match.group(1))
                    if pct > 15:
                        result.requires_escalation = True
                        result.authority = "Bijoy"
                        result.reason = (
                            f"Discount of {pct}% exceeds 15% threshold. "
                            "Bijoy's approval is REQUIRED -- no exceptions."
                        )
                    else:
                        result.requires_escalation = True
                        result.region = self._detect_region(message)
                        result.authority = self._route_pricing_authority(result.region, message)
                        result.reason = (
                            f"Discount of {pct}% requires approval from {result.authority}."
                        )
                else:
                    # Discount mentioned but no percentage -- escalate conservatively
                    result.requires_escalation = True
                    result.authority = "Bijoy"
                    result.reason = (
                        "Discount request without specified percentage. "
                        "Routing to Bijoy for approval."
                    )

                result.discount_approved = False  # NEVER approve (CR-2)
                result.price_generated = False
                break

        return result

    def _detect_region(self, message: str) -> Optional[str]:
        """Detect region from message text."""
        for region, patterns in _REGION_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, message, re.IGNORECASE):
                    return region
        return None

    def _route_pricing_authority(self, region: Optional[str], message: str) -> str:
        """Route to correct pricing authority based on region and value."""
        lower_msg = message.lower()

        # Check for discount > 15% first (always Bijoy)
        pct_match = re.search(r"(\d+)\s*%", lower_msg)
        if pct_match and int(pct_match.group(1)) > 15:
            return "Bijoy"

        if region == "UAE":
            # Check if value > AED 100/LM
            sar_match = re.search(r"(?:AED|aed)\s*(\d[\d,]*)", lower_msg)
            if sar_match:
                value = int(sar_match.group(1).replace(",", ""))
                if value >= 100:
                    return "Bijoy"
            return "Shylesh"

        elif region == "KSA":
            # Check if value > SAR 500K
            sar_match = re.search(r"(?:SAR|sar)\s*(\d[\d,]*)", lower_msg)
            if sar_match:
                value = int(sar_match.group(1).replace(",", ""))
                if value >= 500_000:
                    return "Bijoy"
            return "Bijoy"  # Default KSA large deals to Bijoy

        elif region == "India":
            return "Niranjan"

        elif region == "Turkey":
            return "Bijoy"

        else:
            # International/Other/Unknown -> Bijoy (strategic)
            return "Bijoy"

    def run_all_checks(self, message: str) -> dict:
        """
        Run all guardrail checks on a message. Returns a dict with:
        - product_check: ConstraintCheckResult
        - pricing_check: PricingCheckResult
        - discount_check: PricingCheckResult
        - warnings: list of warning strings
        - has_violations: bool
        """
        product_check = self.check_product_constraints(message)
        pricing_check = self.check_pricing_request(message)
        discount_check = self.check_discount_request(message)

        warnings = []
        if product_check.violation:
            warnings.append(product_check.warning)
        if pricing_check.is_pricing_request:
            warnings.append(
                f"Pricing request detected. Authority: {pricing_check.authority}. "
                "Bot will NOT generate a price."
            )
        if discount_check.discount_requested:
            warnings.append(discount_check.reason)

        return {
            "product_check": product_check,
            "pricing_check": pricing_check,
            "discount_check": discount_check,
            "warnings": warnings,
            "has_violations": product_check.violation,
        }
