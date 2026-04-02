# Bijon Telegram Bot — V2.1

A domain-specific Telegram bot for Bijon (construction products) that integrates Claude API, product constraint guardrails, and full audit logging to Supabase.

**V2.1 adds:** SPEC.md, product eligibility guardrails, `bot_audit_log` audit trail, and escalation rules.

---

## Quick Start

```bash
git clone https://github.com/AnuragGupta181/Bijon_telegram_bot
cd Bijon_telegram_bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in your keys
# Run schema.sql in Supabase SQL Editor
python bot.py
```

---

## Stack

| Layer | Tool |
|---|---|
| Bot framework | `python-telegram-bot` v21 |
| LLM | Claude (`claude-sonnet-4-20250514`) |
| Database | Supabase (Postgres) |
| Runtime | Python 3.12 |

---

## Supabase Setup

Run `schema.sql` in Supabase → SQL Editor. Creates 3 tables:

| Table | Purpose |
|---|---|
| `conversations` | Full message history per user |
| `products` | Product constraints — source of truth for guardrails |
| `bot_audit_log` | Every bot action logged before responding |

### `bot_audit_log` columns

| Column | Type | Description |
|---|---|---|
| `action_type` | text | `LLM_RESPONSE`, `QUOTE_GENERATED`, `GUARDRAIL_TRIGGERED`, `PRODUCT_NOT_FOUND`, `ESCALATED`, `HIGH_VALUE_ESCALATION`, `COMPLIANCE_QUERY`, `ERROR` |
| `input_text` | text | What the user sent |
| `output_text` | text | What the bot replied |
| `warnings` | text[] | Guardrail warnings fired |
| `product_code` | text | Product involved (if any) |
| `quote_value` | numeric | Estimated quote value in INR |
| `escalated` | boolean | Whether escalation was triggered |

---

## Guardrail: WTZ-1800 Submerged Application (VT-01)

**Test:** Send `"Quote WTZ-1800 for submerged pool joint"`

**Expected:** Guardrail fires, no quote generated, `GUARDRAIL_TRIGGERED` logged, WTZ-3400S suggested.

**How it works:**
1. Regex extracts `WTZ-1800` from message.
2. Bot queries `products` table → fetches `disallowed_applications`.
3. Checks each keyword against user's application description.
4. `"pool"` matches → guardrail fires before any quote is generated.
5. Reply sent + audit log written.

WTZ-1800 is blocked for any of: `submerged`, `underwater`, `pool`, `sump`, `tank`, `below-waterline`, `hydrostatic`, `immersion`, `wet-area-floor` — regardless of phrasing.

---

## Architecture

```
User (Telegram)
      │
      ▼
  bot.py (python-telegram-bot v21, async polling)
      │
      ├─► Compliance keyword check → escalate immediately
      │
      ├─► Product code detected?
      │       ├─► Query Supabase `products` table
      │       ├─► Check `disallowed_applications` vs user description
      │       ├─► GUARDRAIL_TRIGGERED → reply + audit log → stop
      │       └─► Valid → QUOTE_GENERATED → reply + audit log
      │
      └─► General query → Claude API → LLM_RESPONSE → reply + audit log
              │
              ▼
         Supabase: bot_audit_log + conversations
```

---

## (a) Context Degradation in Long Agents

In multi-turn LLM agents, context degrades in three ways:

**1. Token window pressure** — As history grows, older turns get truncated. Critical early context (e.g. the user's stated application type) is lost while recent messages remain. Mitigated here by capping history at 10 turns (`MAX_HISTORY`).

**2. Attention dilution** — Transformers attend to all tokens, but in very long contexts, early tokens receive less effective attention weight. Constraints stated early ("this is for submerged use") may be effectively ignored even if within the token window.

**3. Instruction drift** — System prompt weight diminishes relative to a growing history. The model may gradually drift from its constraints over many turns.

**This bot's approach:** Guardrails are database-driven and deterministic — they never pass through the LLM. Product eligibility is checked in Python code against Supabase, so LLM context degradation cannot bypass them.

---

## (b) 5 Escalation Rules

| # | Trigger | Action |
|---|---|---|
| ESC-01 | Compliance query (fire rating, IS code, BIS, NBC, structural) | Immediate → engineering team |
| ESC-02 | Product code not found in `products` table | Cannot quote — flag to team |
| ESC-03 | Guardrail fires on disallowed application | Hard block + escalate |
| ESC-04 | Estimated quote ≥ ₹5,00,000 | High-value → human sign-off required |
| ESC-05 | Claude API error | Ops alert — don't leave user without response |

---

## (c) JIORP Spec — "Generate GCC Quotation"

**Job:** Generate a GCC project quotation for a Bijon product.

**Input:**
- Product code (validated against `products` table)
- Application description (checked against `disallowed_applications`)
- Quantity (units/sqm/ltr)
- Site location (GCC country — affects freight and VAT)

**Output:**
- Product name, code, unit price (USD), extended price, VAT (5%), freight estimate, validity (30 days)
- Constraint warning if application is borderline

**Rules:**
- R1: Product must be `is_active = true` in `products` table
- R2: Application must not match any `disallowed_applications`
- R3: GCC VAT = 5% flat across all 6 member states
- R4: Quote > USD 50,000 → escalate to regional manager
- R5: Every quote logged to `bot_audit_log` with `action_type = QUOTE_GENERATED`

**Processing:**
1. Validate product code → Supabase query
2. Run application eligibility → guardrail check
3. Compute extended price + 5% VAT + freight by country
4. Format output → log to audit → return to user

---

## (d) Token Economics

Using `claude-sonnet-4-20250514`:

| Component | Tokens (approx) |
|---|---|
| System prompt | ~80 |
| 10-turn history window | ~1,500 |
| Product guardrail response | ~100 |
| **Total input per request** | **~1,700** |
| **Output per response** | **~150–300** |

**Cost per turn:**
- Input: 1,700 × ($3/1M) = $0.0051
- Output: 225 × ($15/1M) = $0.0034
- **Total: ~$0.0085/turn**

At 1,000 turns/day → ~$8.50/day → ~$255/month.

**Optimization:** Reduce `MAX_HISTORY` (biggest lever), use Anthropic prompt caching for system prompt, use Haiku for guardrail-only paths that don't need full Sonnet.

---

## (e) Frameworks Beyond LangChain

| Framework | When to use |
|---|---|
| **LangGraph** (used in ccc-ragbot) | Stateful graph agents, multi-step RAG with branching, built-in checkpointing |
| **CrewAI** | Multi-agent tasks mapped to team roles (researcher + writer + reviewer) |
| **Haystack** | Document-heavy RAG, enterprise search, production indexing pipelines |
| **Semantic Kernel** | Azure/.NET stacks, plugin-based agent architecture |
| **Direct SDK** (this bot) | Guardrail-heavy systems where framework abstraction would hide critical logic |

This bot deliberately avoids frameworks — guardrail logic is deterministic and database-driven. Adding LangChain here would add abstraction with no benefit and make it harder to audit the guardrail path.

---

## Issues Hit During Development

1. **`python-telegram-bot` v21 async** — Fully async; `Updater` is gone. `ApplicationBuilder` is the correct pattern.
2. **`service_role` vs `anon` key** — `anon` key blocked server-side inserts due to RLS. `service_role` bypasses RLS for backend writes safely.
3. **Claude alternating roles** — Strict `user → assistant` alternation required. Appending assistant reply immediately prevents validation errors.
4. **Postgres `text[]` arrays** — Supabase returns `text[]` columns as Python lists. Iterating `disallowed_applications` works cleanly.
5. **`load_dotenv()` ordering** — Must be called before any `os.environ[]` reads. First run failed with `KeyError` until this was fixed.