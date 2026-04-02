# Genotek Sales Support Telegram Bot

A Telegram bot built on **python-telegram-bot**, **LangGraph/LangChain**, **AWS Bedrock** (Claude models), and **Supabase** (pgvector) that serves as a sales support agent for Genotek Global's expansion joint cover business.

Built from verified data: **14,145 emails | 3,565 threads | 211 projects | 18 months**.

---

## 🛠️ Local Setup

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Python** | 3.10+ (recommended 3.11) | [python.org/downloads](https://www.python.org/downloads/) |
| **pip** | Latest | Ships with Python |
| **Git** | Any recent version | [git-scm.com](https://git-scm.com/) |
| **AWS Account** | — | With Bedrock access enabled for Claude models |
| **Supabase Project** | — | Free tier works ([supabase.com](https://supabase.com/)) |
| **Telegram Bot Token** | — | Create via [@BotFather](https://t.me/BotFather) |

---

### Step 1 — Clone the Repository

```bash
git clone https://github.com/AnuragGupta181/Genotek_Sales_Agent.git
cd Genotek_Sales_Agent
```

---

### Step 2 — Create a Virtual Environment

<details>
<summary><strong>🐧 Linux / macOS</strong></summary>

```bash
# Create the virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate
```

</details>

<details>
<summary><strong>🪟 Windows (PowerShell)</strong></summary>

```powershell
# Create the virtual environment
python -m venv venv

# Activate it
.\venv\Scripts\Activate.ps1
```

> **Note:** If you get a script-execution policy error, run this first (as Administrator):
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

</details>

<details>
<summary><strong>🪟 Windows (Command Prompt)</strong></summary>

```cmd
python -m venv venv
venv\Scripts\activate.bat
```

</details>

---

### Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

---

### Step 4 — Configure Environment Variables

```bash
# Linux / macOS
cp .env.example .env

# Windows (PowerShell)
Copy-Item .env.example .env

# Windows (Command Prompt)
copy .env.example .env
```

Open `.env` in your editor and fill in the required values:

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Token from [@BotFather](https://t.me/BotFather) |
| `AWS_ACCESS_KEY_ID` | Your AWS IAM access key |
| `AWS_SECRET_ACCESS_KEY` | Your AWS IAM secret key |
| `AWS_REGION` | AWS region with Bedrock access (e.g. `us-east-1`) |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Supabase service-role key (not the anon key) |

---

### Step 5 — Set Up Supabase Schema

1. Open your Supabase dashboard → **SQL Editor**.
2. Paste the contents of `schema/supabase_schema.sql`.
3. Click **Run** to create all required tables (`conversations`, `bot_audit_log`, `products`, `suppliers`, `pricing_rules`) and enable the `pgvector` extension.

---

### Step 6 — Run the Bot

```bash
python -m bot.main
```

The bot will start polling Telegram for messages. You should see startup logs in the terminal.

---

### 🐳 Alternative: Run with Docker

If you prefer Docker, you can skip the virtual-environment steps above.

<details>
<summary><strong>🐧 Linux / macOS</strong></summary>

```bash
# Make sure .env is configured (Step 4 above), then:
docker compose up --build -d

# View logs
docker compose logs -f bot
```

</details>

<details>
<summary><strong>🪟 Windows</strong></summary>

1. Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/).
2. Make sure Docker Desktop is running.
3. Open PowerShell in the project directory:

```powershell
# Make sure .env is configured (Step 4 above), then:
docker compose up --build -d

# View logs
docker compose logs -f bot
```

</details>

To stop the container:

```bash
docker compose down
```

---

### Troubleshooting

| Issue | Fix |
|-------|-----|
| `python` not recognized (Windows) | Re-install Python and check **"Add Python to PATH"** during setup |
| `venv\Scripts\Activate.ps1` cannot be loaded | Run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` in an Admin PowerShell |
| `ModuleNotFoundError` after install | Make sure the virtual environment is **activated** before running `pip install` |
| `boto3` / Bedrock auth errors | Verify `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and that Bedrock model access is enabled in the AWS console |
| Docker build fails on Windows | Ensure Docker Desktop has WSL 2 backend enabled (Settings → General) |

---

## Architecture

```
Telegram User
     |
     v
python-telegram-bot (handlers.py)
     |
     v
LangGraph Workflow (graph.py)
  |-- Node 1: Load conversation history (Supabase)
  |-- Node 2: Run guardrails (guardrails.py)
  |       |-- Product constraint checks
  |       |-- Pricing authority routing
  |       |-- Discount escalation detection
  |-- [Conditional] Violation? -> Block + respond with warning
  |-- Node 3: Route model (models.py)
  |       |-- Haiku  (~80%) -> triage, classification
  |       |-- Sonnet (~15%) -> quote drafting, routing
  |       |-- Opus   (~5%)  -> complex pricing logic
  |-- Node 4: Generate response (AWS Bedrock)
  |-- Node 5: Store + Audit (Supabase)
  |       |-- conversations table (every turn)
  |       |-- bot_audit_log table (every action)
     |
     v
Response to User
```

---

## Quick Start

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Copy .env.example to .env and fill in credentials
cp .env.example .env

# 3. Run Supabase schema (paste schema/supabase_schema.sql in Supabase SQL Editor)

# 4. Start the bot
python -m bot.main
```

---

## (a) Context Degradation in Long-Running Agents

### The Problem

LLMs process text within a fixed context window (Claude 3.5: 200K tokens). In a long-running sales agent that handles 16 quotes/day across months of operation, context degradation manifests in three ways:

1. **Attention dilution**: As the context window fills, the model's attention to earlier instructions weakens. Critical rules like "NEVER set prices" can be overridden by patterns in conversation history that implicitly discuss numbers. Research shows instruction-following accuracy drops by 15-30% when context exceeds 100K tokens.

2. **Recency bias**: The model prioritizes recent conversation turns over system instructions. If the last 5 messages discuss pricing numbers (from a human authority response copied into chat), the model may start generating prices itself, violating SPEC.md CR-1.

3. **Memory hallucination**: In long sessions, the model may "remember" conversations that didn't happen, or merge details from different clients/projects. A quote for a KSA project could contaminate context for a subsequent UAE query.

### Mitigation Strategy in This Bot

| Strategy | Implementation | File |
|----------|---------------|------|
| **Rolling window** | Last 20 turns only (configurable via `MAX_CONVERSATION_HISTORY`) | `config.py` |
| **System prompt anchoring** | Critical rules (no pricing, no discounts, no delivery dates) placed in system prompt, never in conversation history | `config.py` |
| **Stateless graph execution** | Each message runs a fresh LangGraph invocation with history loaded from DB, not accumulated in memory | `graph.py` |
| **Embedding-based retrieval** | For long-term memory, pgvector similarity search replaces full history injection | `supabase_client.py` |
| **Session rotation** | Sessions can be rotated daily/weekly to prevent unbounded growth | `handlers.py` |
| **Guardrails as hard gates** | Product constraints and pricing rules are checked BEFORE the LLM sees the message, not as prompt instructions the LLM might ignore | `guardrails.py` |

### Why This Matters for Genotek

With 16 quotes/day and conversations spanning regions (UAE, KSA, India, SEA), context contamination is a real risk. A single misrouted pricing request (e.g., India pricing sent to Shylesh instead of Niranjan) could delay a quote by days. The stateless architecture ensures each message is processed with clean context.

---

## (b) Five Escalation Rules

These rules are enforced programmatically in `guardrails.py` (not just as LLM instructions):

### Rule 1: Pricing Authority by Region
Every pricing request is routed to the correct human authority based on region. The bot **never** generates a price.

| Region | Route To | Condition |
|--------|----------|-----------|
| UAE | Shylesh | Items < AED 100/LM |
| KSA | Bijoy | Deals > SAR 500K |
| India | Niranjan | All (Pidilite channel) |
| International | Bijoy | All other regions |

### Rule 2: Discount Authority (>15% = Bijoy Always)
Any discount request above 15% is hard-routed to Bijoy with zero exceptions. Below 15% routes to the regional authority. The bot **never** approves a discount.

### Rule 3: Product Constraint Violations Block Processing
If a product is mentioned in an application that violates its constraints (e.g., WTZ-1800 for submerged use), the entire quote routing is **blocked**. No LLM is invoked. A hard-coded warning is returned with an alternative product suggestion.

### Rule 4: Deal Death Detection (96-Day Threshold)
Quotes older than 96 days with no follow-up are flagged as dead deals. At Day 30, Bijoy is alerted. At Day 60, final re-engagement or archive decision is required.

### Rule 5: Delivery Date Non-Commitment
The bot **never** commits to a delivery date. It provides known lead time ranges (e.g., "Turkey: 29 days standard", "RY dies: 75-85 days") with an explicit "UNCONFIRMED -- requires supplier verification" disclaimer.

---

## (c) Spec: "Generate GCC Quotation"

### Use Case
User: "Generate a quotation for the Al Maktoum Airport expansion joint project in Dubai"

### Spec

```
TRIGGER: User requests quote generation for a GCC (UAE/KSA/Oman/Bahrain/Qatar/Kuwait) project.

PRECONDITIONS:
  - Product codes identified (from message or conversation history)
  - Region classified as GCC
  - Client name/company extracted

FLOW:
  1. CLASSIFY region -> GCC (specific country)
  2. CHECK product constraints for all mentioned products
     - If violation -> BLOCK, return warning, suggest alternatives
  3. ROUTE pricing to authority:
     - UAE < AED 100/LM -> Shylesh
     - KSA > SAR 500K -> Bijoy
     - All GCC discounts > 15% -> Bijoy
  4. DRAFT quote shell (template only, NO prices):
     - File naming: [Country].[ProductType].[ProjectName].[AK].[Rev01]
     - Greeting: "Dear [Client Name]"
     - Products listed with codes and descriptions
     - Placeholder: "[PRICING: Awaiting {authority} approval]"
     - Sign-off: "Best Regards;"
     - BCC: tracking copy
  5. PRESENT draft to AK for review (Trust Level 0)
  6. LOG to audit trail:
     - action_type: QUOTE_ROUTE
     - All products, region, authority, template used
  7. SCHEDULE follow-up: Day 3/7/14/30 cadence

POSTCONDITIONS:
  - Quote draft stored in conversations table
  - Audit log entry created
  - Follow-up timers set
  - Pricing request routed to correct authority
  - NO price numbers in the draft

HARD CONSTRAINTS:
  - Agent NEVER fills in price fields
  - Agent NEVER sends to client (Trust Level 0)
  - Agent NEVER commits delivery dates
  - All GCC quotes use formal English ("Dear", not "Hello")
```

---

## (d) Token Economics Math

### Cost Model (AWS Bedrock Pricing)

| Model | Input $/1M tokens | Output $/1M tokens | Usage % | Typical Task |
|-------|-------------------|---------------------|---------|-------------|
| Claude 3.5 Haiku | $0.25 | $1.25 | 80% | Triage, classify, remind |
| Claude 3.5 Sonnet v2 | $3.00 | $15.00 | 15% | Quote drafting, routing |
| Claude 3 Opus | $5.00 | $25.00 | 5% | Complex pricing logic |

### Daily Volume Estimate

Genotek processes **16 quotes/business day** (VERIFIED from Q1 data).

```
Per quote interaction (avg):
  - User message:    ~200 tokens input
  - System prompt:   ~500 tokens (cached after first call)
  - History context: ~2,000 tokens (last 20 turns)
  - Response:        ~400 tokens output

Per quote total: ~2,700 input + ~400 output = ~3,100 tokens

Daily (16 quotes + ~32 follow-up/misc interactions = 48 interactions):
  - Haiku  (80%, 38 calls): 38 * 3,100 = 117,800 tokens
  - Sonnet (15%,  7 calls):  7 * 3,100 =  21,700 tokens
  - Opus   (5%,   3 calls):  3 * 3,100 =   9,300 tokens
```

### Monthly Cost Calculation (22 business days)

```
Haiku:
  Input:  117,800 * 22 = 2,591,600 tokens/mo * $0.25/1M  = $0.65
  Output:  15,200 * 22 =   334,400 tokens/mo * $1.25/1M  = $0.42
  Haiku subtotal: $1.07/month

Sonnet:
  Input:   21,700 * 22 =   477,400 tokens/mo * $3.00/1M  = $1.43
  Output:   2,800 * 22 =    61,600 tokens/mo * $15.00/1M = $0.92
  Sonnet subtotal: $2.35/month

Opus:
  Input:    9,300 * 22 =   204,600 tokens/mo * $5.00/1M  = $1.02
  Output:   1,200 * 22 =    26,400 tokens/mo * $25.00/1M = $0.66
  Opus subtotal: $1.68/month

TOTAL LLM COST: ~$5.10/month at current volume
```

### With Growth Buffer (3x volume)

```
At 48 quotes/day (3x growth):
  Total: ~$15.30/month

At 100 quotes/day (extreme growth):
  Total: ~$31.88/month
```

### Infrastructure Costs

```
Supabase:    Free tier (up to 500MB, 50K rows) -> $0/month
             Pro tier if needed: $25/month
AWS Bedrock: Pay-per-use (included above)
Telegram:    Free
Total:       $5-32/month (LLM) + $0-25/month (Supabase) = $5-57/month
```

This is well within Bijoy's **$15-40/month** target at normal volume.

### Prompt Caching Economics (from Claude Code Leak)

The system prompt (~500 tokens) is identical across all calls. AWS Bedrock supports prompt caching, which reduces input costs by up to 90% for cached prefixes. With caching:

```
Effective cost with caching: ~$3-4/month at 16 quotes/day
```

---

## (e) Frameworks Beyond LangChain

### Why Not Just LangChain?

LangChain is used here as the **message abstraction layer** (HumanMessage, AIMessage, SystemMessage) and **LangGraph** for the stateful workflow. But for production scaling, several alternatives were evaluated:

### Framework Comparison

| Framework | Strengths | Weaknesses | Genotek Fit |
|-----------|-----------|------------|-------------|
| **LangGraph** (used) | Stateful graphs, conditional routing, human-in-the-loop gates | Python only, debugging opaque | HIGH - workflow matches sales support flow |
| **OpenClaw** (247K GitHub stars) | Open-source, WhatsApp/Telegram native, Skills system (SKILL.md), self-extending, multi-model routing | Security concerns with community skills, newer ecosystem | HIGH for Phase 2 - adds WhatsApp layer for AK |
| **AgentScope** (Alibaba-backed) | Multi-agent orchestration, ReAct agent, MCP+A2A protocol, memory with compression, visual Studio frontend | Over-engineered for 1-person build, steeper learning curve | MEDIUM - revisit when team grows |
| **CrewAI** | Multi-agent task delegation, role-based agents, process types (sequential/hierarchical) | Less flexible than LangGraph for custom flows, opinionated architecture | LOW - too rigid for Genotek's escalation matrix |
| **AutoGen** (Microsoft) | Multi-agent conversation, code execution, group chat patterns | Heavy framework, complex setup, enterprise-oriented | LOW - overkill for 16 quotes/day |
| **Semantic Kernel** (Microsoft) | .NET/Python/Java, enterprise plugins, planner with LLM | Microsoft ecosystem lock-in, less Python-native feel | LOW - wrong ecosystem |
| **Haystack** (deepset) | RAG-focused, pipeline architecture, production-ready retrieval | RAG-first design doesn't match sales workflow needs | LOW - wrong primary use case |
| **DSPy** (Stanford) | Programmatic prompt optimization, automatic few-shot learning | Research-oriented, less production tooling | NICHE - useful for prompt optimization layer |

### Recommended Path

```
Phase 1 (NOW):   LangGraph + LangChain + AWS Bedrock + Supabase
                  Reason: Fast to build, matches workflow, Bedrock = enterprise-grade

Phase 2 (Week 2): Add OpenClaw for WhatsApp interface
                   Reason: AK needs WhatsApp (not just Telegram), native multi-model routing

Phase 3 (Month 2): Evaluate AgentScope for multi-agent orchestration
                    Reason: When multiple team members use the agent simultaneously
```

### Why AWS Bedrock Over Direct API?

| Factor | Bedrock | Direct Anthropic API |
|--------|---------|---------------------|
| Auth | IAM (existing AWS infra) | API key management |
| Compliance | SOC2, HIPAA, ISO by default | Requires separate verification |
| Model access | Claude + Llama + Mistral + Titan | Claude only |
| Logging | CloudWatch integration | Manual |
| Cost | Same token pricing | Same token pricing |
| Latency | ~50-100ms overhead | Direct |

For Genotek: Bedrock is preferred for compliance and multi-model optionality. Direct API is included (commented) as a simpler fallback.

---

## Project Structure

```
telegram_bot/
├── SPEC.md                    # Part 0: Correctness specification
├── README.md                  # This file
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variable template
├── schema/
│   └── supabase_schema.sql    # Supabase table creation SQL
├── bot/
│   ├── __init__.py
│   ├── main.py                # Entry point
│   ├── config.py              # Configuration + model routing constants
│   ├── models.py              # Model router (Bedrock + direct API)
│   ├── handlers.py            # Telegram command/message handlers
│   ├── guardrails.py          # Product constraints + pricing authority
│   ├── audit.py               # Audit trail logging
│   ├── supabase_client.py     # Supabase operations
│   └── graph.py               # LangGraph workflow
└── tests/
    ├── __init__.py
    ├── test_guardrails.py     # Product + pricing + discount tests
    └── test_models.py         # Model routing tests
```

---

## Supabase Tables

| Table | Purpose | Key Fields |
|-------|---------|-----------|
| `conversations` | Every conversation turn | user_id, role, content, model_used, embedding (pgvector) |
| `bot_audit_log` | Every bot action | action_type, input_text, output_text, warnings, latency_ms |
| `products` | Product catalog + constraints | product_code, application_constraints (JSONB), supplier_name |
| `suppliers` | Supplier data | name, avg_lead_days, payment_status, known_issues |
| `pricing_rules` | Escalation rules | region, condition_desc, route_to, is_verified |

---

## Running Tests

```bash
pytest tests/ -v
```

Tests cover:
- **VT-1**: WTZ-1800 submerged pool joint constraint violation
- **VT-2**: Pricing authority routing (UAE -> Shylesh, KSA -> Bijoy, India -> Niranjan)
- **VT-3**: Discount escalation (>15% -> Bijoy always)
- **VT-6**: Model routing (simple -> Haiku, medium -> Sonnet, complex -> Opus)
