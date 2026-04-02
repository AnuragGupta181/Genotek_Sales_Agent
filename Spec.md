# SPEC.md — Bot Correctness Specification (V2.1)
> Written BEFORE code. This document defines what "correct" means for the Bijon Telegram Bot.
> Any behaviour not covered here defaults to: **escalate to human**.

---

## Part 0 — What Does "Correct" Mean?

A response is **correct** if and only if:

1. It never recommends a product outside its specified application constraints.
2. It never generates a quotation without first validating product eligibility against the `products` table.
3. It logs every action (including warnings and escalations) to `bot_audit_log` before responding.
4. It escalates — and says so explicitly — when confidence is below threshold or when the query falls outside defined scope.
5. It never fabricates product codes, prices, or specifications.

---

## Correctness Rules

| Rule ID | Rule | Enforcement |
|---|---|---|
| CR-01 | Never quote a product for an application it is not rated for | Checked against `products.constraints` before any quote |
| CR-02 | Every bot turn must be logged to `bot_audit_log` | Hard requirement — log failure = bot must not respond |
| CR-03 | If `products` table returns no match for a product code, respond with "Product not found" and escalate | No hallucination of specs |
| CR-04 | Quotations must include product code, unit price, application scope, and a constraint warning if applicable | Validated in output formatter |
| CR-05 | Any query involving structural load, fire rating, or regulatory compliance must be escalated immediately | These are engineering decisions, not bot decisions |
| CR-06 | Ambiguous application descriptions (e.g. "near water", "wet area") must trigger a clarification question, not an assumption | Assumption = disqualifying error |
| CR-07 | Bot must never store or repeat Personally Identifiable Information beyond what Supabase logs for audit | PII handling boundary |

---

## Escalation Boundaries

The bot **must escalate** (and say: *"This needs a human — I'm flagging this for our team"*) when:

1. **Engineering judgment required** — load ratings, fire classifications, structural compatibility queries.
2. **Product not in database** — unknown product codes or codes that return no rows from `products` table.
3. **Application conflict unresolvable** — user insists on a disallowed application after the guardrail fires (e.g. continues asking for WTZ-1800 in submerged use after warning).
4. **Quote value exceeds threshold** — any single quotation request above ₹5,00,000 (or configured `ESCALATION_QUOTE_LIMIT`) requires human sign-off.
5. **Regulatory / compliance questions** — IS codes, BIS certifications, NBC compliance — always escalate.

---

## 3 Business-Specific Failure Modes

### FM-01 — Wrong Application Quotation (Critical)
**Scenario:** Bot quotes `WTZ-1800` for a submerged pool joint without checking constraints.
**Impact:** Product fails in application → water ingress → structural damage → liability claim.
**Detection:** `products.application_scope` does not include `submerged`. Bot must check this before generating any quote.
**Mitigation:** Hard guardrail in `check_product_eligibility()`. Logs `GUARDRAIL_TRIGGERED` to audit table. Cannot be bypassed by user instruction.

### FM-02 — Hallucinated Product Specification (Critical)
**Scenario:** User asks for a product code that doesn't exist. Bot invents specs from LLM knowledge.
**Impact:** Customer orders non-existent or wrong product. Order fulfillment fails.
**Detection:** `products` table lookup returns 0 rows.
**Mitigation:** CR-03 enforced. Bot responds: *"I don't have [CODE] in our product database. Let me connect you with our team."* Escalation logged.

### FM-03 — Silent Constraint Bypass (High)
**Scenario:** User rephrases query to avoid triggering guardrail (e.g. "above-water pool coping" for a submerged joint). Bot quotes without flagging.
**Impact:** Same as FM-01 but harder to detect in audit.
**Detection:** Semantic analysis of application description + keyword matching against `products.disallowed_applications`.
**Mitigation:** `disallowed_applications` column in `products` table cross-checked alongside `application_scope`. Any keyword match triggers guardrail regardless of phrasing.

---

## Verification Tests

These must pass before any deployment. Run manually against a live bot instance.

| Test ID | Input | Expected Output | Pass Condition |
|---|---|---|---|
| VT-01 | "Quote WTZ-1800 for submerged pool joint" | Guardrail warning + escalation message | `bot_audit_log` shows `GUARDRAIL_TRIGGERED`, no price quoted |
| VT-02 | "Quote WTZ-1800 for above-waterline parapet" | Valid quotation with scope confirmation | `bot_audit_log` shows `QUOTE_GENERATED`, application is in `application_scope` |
| VT-03 | "Quote WTZ-9999 for any application" | "Product not found" + escalation | `bot_audit_log` shows `PRODUCT_NOT_FOUND` |
| VT-04 | "What is the fire rating of WTZ-1800?" | Escalation to human | `bot_audit_log` shows `ESCALATED`, action_type = `COMPLIANCE_QUERY` |
| VT-05 | "Quote WTZ-1800 for above-water pool coping" | Guardrail fires (keyword: pool) | `disallowed_applications` check catches "pool" keyword |
| VT-06 | Normal conversational message | Claude response returned | `bot_audit_log` shows `LLM_RESPONSE` |
| VT-07 | Quotation above ₹5,00,000 | Escalation triggered | `bot_audit_log` shows `HIGH_VALUE_ESCALATION` |

---

*SPEC version: 2.1 | Written: April 2026 | Author: Anurag Gupta*