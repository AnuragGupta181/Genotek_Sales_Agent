# SPEC.md -- Genotek Sales Support Telegram Bot

## Part 0: Specification Before Code

**Purpose**: Define what "correct" means BEFORE any code is written.
This document establishes the contract between the bot's behavior and Genotek Global's
operational requirements. Every code path must trace back to a rule defined here.

---

## 1. System Identity

| Field | Value |
|-------|-------|
| System Name | Genotek Sales Support Agent (Telegram) |
| Role | Sales Support Agent -- NOT an autonomous sales manager |
| Data Source | 14,145 emails, 3,565 threads, 211 projects, 18 months verified data |
| Primary User | AK (Anutashaya Kumar) -- 86% email traffic handler |
| Approval Chain | Bijoy (CEO) > Shylesh (COO) > Niranjan (India) > AK (Ops) |

---

## 2. Correctness Rules

### CR-1: The Agent Never Sets Prices
- **Rule**: The bot MUST NEVER generate, calculate, or suggest a final price.
- **Rationale**: AK has 0% pricing authority (VERIFIED from audit). Every price
  requires human escalation to Bijoy, Shylesh, or Niranjan.
- **Enforcement**: Any message containing price requests must be routed to the
  appropriate pricing authority. The bot responds with routing info, never numbers.
- **Test**: Send "What's the price for WTZ-1200 for UAE project?" -> Bot must NOT
  return a price. Must indicate escalation to Shylesh (UAE < AED 100/LM) or Bijoy.

### CR-2: The Agent Never Approves Discounts
- **Rule**: The bot MUST NEVER approve, suggest, or imply a discount percentage.
- **Rationale**: Discounts > 15% require Bijoy ALWAYS (VERIFIED). Under 15% requires
  Shylesh or Niranjan depending on region.
- **Enforcement**: Discount-related queries are flagged and escalated.
- **Test**: Send "Can we offer 20% discount on KSA order?" -> Bot must flag as
  requiring Bijoy's explicit approval.

### CR-3: The Agent Never Commits Delivery Dates
- **Rule**: The bot MUST NEVER promise, confirm, or estimate delivery dates without
  explicit supplier confirmation stored in the system.
- **Rationale**: Lead times vary wildly (29 days Turkey standard, 75-85 days RY
  Extrusion dies). Committing dates without supplier confirmation creates liability.
- **Enforcement**: Delivery queries return known lead time ranges with explicit
  "UNCONFIRMED -- requires supplier verification" disclaimer.
- **Test**: Send "When can we deliver RY aluminum profiles?" -> Bot returns 75-85 day
  range with UNCONFIRMED flag, not a specific date.

### CR-4: Product Constraint Enforcement
- **Rule**: The bot MUST validate product application constraints before any
  recommendation or quote routing.
- **Rationale**: Products have specific application boundaries. Recommending a product
  outside its rated environment creates safety and liability risk.
- **Enforcement**: Product constraint table checked on every product mention.
  Violations generate a WARNING in response and audit log.
- **Test**: Send "Quote WTZ-1800 for submerged pool joint" -> Bot must flag that
  WTZ-1800 is above-waterline only. Must NOT proceed with quote routing.

### CR-5: Every Action Gets Audited
- **Rule**: Every bot interaction MUST be logged to `bot_audit_log` with timestamp,
  action type, full input, full output, and any warnings generated.
- **Rationale**: Audit trail is non-negotiable for a system that touches sales data.
- **Enforcement**: Logging wraps every handler. Failed logs trigger alert.
- **Test**: Send any message -> Verify `bot_audit_log` row created with all fields.

### CR-6: Conversation Continuity
- **Rule**: Every conversation turn MUST be stored in Supabase with user_id,
  session context, timestamps, and model used.
- **Rationale**: Open Brain memory architecture requires persistent storage for
  client preferences, quote history, and deal lifecycle state.
- **Enforcement**: Conversation storage is synchronous -- bot does not respond until
  storage is confirmed.
- **Test**: Send 3 messages in sequence -> Verify all 3 stored with correct ordering.

### CR-7: Model Routing Correctness
- **Rule**: The bot MUST route tasks to the appropriate Claude model:
  - Haiku (claude-3-5-haiku) for triage/classification (~80% of tasks)
  - Sonnet (claude-3-5-sonnet-v2) for quote drafting/routing (~15% of tasks)
  - Opus (claude-3-opus) for complex pricing logic/exceptions (~5% of tasks)
- **Rationale**: Token cost optimization. $15-40/month target at 16 quotes/day.
- **Enforcement**: Task classifier runs before model invocation.
- **Test**: Send "Hi" -> Haiku. Send "Draft quote for UAE project" -> Sonnet.
  Send "Complex multi-region pricing exception" -> Opus.

---

## 3. Escalation Boundaries

### EB-1: Pricing Escalation Matrix

| Condition | Route To | Authority Level | Verified |
|-----------|----------|-----------------|----------|
| UAE < AED 100/LM | Shylesh | Auto-approve small | VERIFIED |
| KSA > SAR 500K | Bijoy | Large deal | VERIFIED |
| India | Niranjan | Pidilite channel | VERIFIED |
| Discount > 15% | Bijoy ALWAYS | No exceptions | VERIFIED |
| Turkey custom | Ankara Factory | 29-day baseline | VERIFIED |
| International/Other | Bijoy | Strategic | VERIFIED |

### EB-2: Follow-Up Escalation Cadence (ASSUMED -- needs Bijoy validation)

| Day | Action | Escalation |
|-----|--------|------------|
| 3 | First follow-up: confirm receipt | Agent auto-draft |
| 7 | Second follow-up: questions on specs/pricing? | Agent auto-draft |
| 14 | Third follow-up: timeline for decision? | Agent auto-draft |
| 30 | Escalate to Bijoy: "Deal going cold" | Human required |
| 60 | Final: Bijoy decides re-engage or archive | Human required |
| 96 | Dead deal threshold | Auto-archive |

### EB-3: PO Approval Escalation

| Condition | Route To | SLA (ASSUMED) |
|-----------|----------|---------------|
| Any PO | Shylesh first | 48 hours |
| Shylesh no response in 48h | Bijoy | Immediate |
| PO value > threshold (TBD) | Bijoy direct | 24 hours |

### EB-4: Supplier Exception Escalation

| Exception Type | First Contact | Escalation |
|----------------|---------------|------------|
| Production delay | AK -> Supplier | Shylesh if > 7 days |
| Payment block | Shylesh | Bijoy if > 30 days |
| Force majeure | Bijoy immediately | -- |
| Quality issue | Shylesh (quality gate) | Bijoy if systemic |

### EB-5: Trust Level Gates

| Level | Behavior | Promotion Criteria (ASSUMED) |
|-------|----------|------------------------------|
| 0 (Current) | Draft only, human sends all | Default start |
| 1 | Auto-send routine, human reviews exceptions | 95% accuracy on 50+ drafts |
| 2 | Auto-routine, flag exceptions only | 98% accuracy on 200+ sends |
| 3 | Autonomous within boundaries | TBD by Bijoy |

---

## 4. Three Business-Specific Failure Modes

### FM-1: Silent Deal Death (The 39.1% Leak)

- **Description**: Quote sent, zero follow-up, deal dies by silence.
- **Evidence**: 1,394 of 3,565 threads (39.1%) received zero follow-up over 18 months.
  At 12% conversion rate = ~167 lost orders.
- **Detection**: Bot monitors all quote threads. Flags any thread with no follow-up
  action after Day 3 post-quote.
- **Mitigation**: Automatic follow-up scheduling at Day 3/7/14/30.
  Escalation to Bijoy at Day 30. Archive at Day 96.
- **Bot Behavior**: If a user asks about a quote that's > 3 days old with no follow-up,
  bot MUST flag it as "at risk of silent death" and recommend follow-up action.
- **Verification Test**:
  ```
  Input: "Check status of Project ABC quote sent 10 days ago"
  Expected: Bot flags as AT RISK (no follow-up detected after Day 7),
            recommends Day 14 follow-up template,
            logs warning to audit trail.
  ```

### FM-2: Product Misapplication (Safety/Liability)

- **Description**: Product recommended or quoted for an application outside its rated
  constraints (e.g., above-waterline product specified for submerged application).
- **Evidence**: Product constraints exist but are not systematically enforced in the
  current manual workflow.
- **Detection**: Product constraint table checked on every product mention.
  Cross-reference product code against application type in query.
- **Mitigation**: Hard block. Bot refuses to proceed with quote routing when constraint
  violation detected. Logs WARNING to audit trail. Suggests correct product if available.
- **Bot Behavior**: When WTZ-1800 is mentioned with "submerged", "underwater",
  "pool joint", or similar below-waterline keywords, bot MUST:
  1. STOP quote processing
  2. Return explicit warning: "WTZ-1800 is rated for above-waterline applications only"
  3. Suggest: "For submerged/below-waterline applications, consider WTZ-2400 series"
  4. Log to audit trail with action_type = "PRODUCT_CONSTRAINT_VIOLATION"
- **Verification Test**:
  ```
  Input: "Quote WTZ-1800 for submerged pool joint"
  Expected: WARNING returned. Quote NOT routed. Audit log entry created
            with action_type="PRODUCT_CONSTRAINT_VIOLATION".
            Alternative product suggested.
  ```

### FM-3: Pricing Authority Bypass

- **Description**: Bot generates or implies a price without proper authority escalation,
  or routes pricing request to wrong authority for the region/value.
- **Evidence**: AK has 0% pricing authority (VERIFIED). 100% of quotes require human
  pricing. Routing errors could send UAE pricing to India authority or vice versa.
- **Detection**: Every pricing-related query checked against escalation matrix (EB-1).
  Region + value + discount level all validated.
- **Mitigation**: Hard block on any price generation. Strict routing validation.
  Mismatch between detected region and routing target triggers WARNING.
- **Bot Behavior**: If query mentions pricing + region, bot MUST:
  1. Classify region correctly (UAE/KSA/India/SEA/Turkey/International)
  2. Route to CORRECT authority per EB-1 matrix
  3. NEVER output a number as a price
  4. Log routing decision to audit trail
- **Verification Test**:
  ```
  Input: "What discount can we offer on the KSA megaproject worth SAR 600K?"
  Expected: Bot identifies KSA + >SAR 500K + discount request.
            Routes to Bijoy (large deal + discount authority).
            Does NOT suggest any discount percentage.
            Audit log shows correct routing decision.
  ```

---

## 5. Verification Tests (Executable)

### VT-1: Product Constraint Guardrail
```python
# test_guardrails.py::test_wtz1800_submerged
input_msg = "Quote WTZ-1800 for submerged pool joint"
result = guardrails.check_product_constraints(input_msg)
assert result.violation == True
assert "above-waterline only" in result.warning
assert result.suggested_alternative is not None
assert result.action_type == "PRODUCT_CONSTRAINT_VIOLATION"
```

### VT-2: Pricing Authority Routing
```python
# test_guardrails.py::test_pricing_never_generated
input_msg = "What's the price for WTZ-1200 for UAE?"
result = guardrails.check_pricing_request(input_msg)
assert result.is_pricing_request == True
assert result.authority == "Shylesh"  # UAE < AED 100/LM
assert result.price_generated == False  # NEVER generate price
```

### VT-3: Discount Escalation
```python
# test_guardrails.py::test_discount_escalation
input_msg = "Can we offer 20% discount on this order?"
result = guardrails.check_discount_request(input_msg)
assert result.requires_escalation == True
assert result.authority == "Bijoy"  # >15% always Bijoy
assert result.discount_approved == False
```

### VT-4: Audit Trail Completeness
```python
# test_audit.py::test_every_action_logged
# Send message through bot pipeline
# Verify bot_audit_log has entry with:
# - timestamp (not null, within last 5 seconds)
# - action_type (not null, valid enum)
# - input_text (matches sent message)
# - output_text (matches bot response)
# - warnings (array, may be empty)
```

### VT-5: Conversation Storage
```python
# test_conversation.py::test_turns_stored
# Send 3 sequential messages
# Query conversations table
# Verify: 3 rows, correct user_id, correct ordering, correct content
```

### VT-6: Model Routing
```python
# test_models.py::test_haiku_for_simple
input_msg = "Hello"
model = router.classify_and_route(input_msg)
assert model.model_id contains "haiku"

# test_models.py::test_sonnet_for_quote
input_msg = "Draft a quote for UAE expansion joint project"
model = router.classify_and_route(input_msg)
assert model.model_id contains "sonnet"

# test_models.py::test_opus_for_complex
input_msg = "Analyze multi-region pricing exception with volume discount tiers"
model = router.classify_and_route(input_msg)
assert model.model_id contains "opus"
```

### VT-7: Dead Deal Detection
```python
# test_followup.py::test_silent_death_detection
# Create quote record with sent_at = 10 days ago, followup_count = 0
result = followup.check_deal_health(quote_id)
assert result.status == "AT_RISK"
assert result.days_silent >= 10
assert result.recommended_action == "SEND_FOLLOWUP_DAY14"
```

---

## 6. Data Integrity Constraints

### Supabase Table Contracts

**conversations**:
- `user_id` MUST NOT be null
- `role` MUST be one of: 'user', 'assistant', 'system'
- `content` MUST NOT be empty string
- `model_used` MUST reference a valid model identifier
- `created_at` MUST be auto-set, never manually overridden

**bot_audit_log**:
- `action_type` MUST be one of: 'MESSAGE', 'QUOTE_ROUTE', 'PRODUCT_CHECK',
  'PRICING_ESCALATION', 'FOLLOWUP_TRIGGER', 'PRODUCT_CONSTRAINT_VIOLATION',
  'DISCOUNT_ESCALATION', 'ERROR'
- `timestamp` MUST be server-side generated (not client-side)
- `input_text` and `output_text` MUST NOT be truncated
- `warnings` is JSONB array, default empty array `[]`

**products**:
- `product_code` MUST be unique
- `application_constraints` MUST NOT be null (every product has boundaries)
- `supplier_id` MUST reference a valid supplier
- `is_active` defaults to true

---

## 7. Non-Functional Requirements

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| Response latency | < 5 seconds (Haiku), < 15s (Sonnet), < 30s (Opus) | User experience |
| Monthly API cost | $15-40 at 16 quotes/day | Bijoy's budget constraint |
| Audit log retention | 2 years minimum | Compliance |
| Conversation history | Last 20 turns per session | Context window management |
| Uptime | Best effort (single-process bot) | Phase 1 is MVP |

---
<!-- 
## 8. Out of Scope (Explicit)

- WhatsApp integration (Phase 2 -- OpenClaw layer)
- Autonomous email sending (requires Trust Level 1+)
- Direct CRM sync (HubSpot MCP -- post-MVP)
- Payment processing
- Installation/warranty tracking (post-delivery gap -- data not available)
- Multi-language support beyond English

--- -->

<!-- ## 9. Revision History

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-04-03 | Initial specification from 18-month email audit | -->

