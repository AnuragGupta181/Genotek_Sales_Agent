-- ─────────────────────────────────────────────────────────────────────────────
-- Bijon Telegram Bot — Supabase Schema V2.1
-- Run in Supabase SQL Editor (Dashboard → SQL Editor → New query)
-- ─────────────────────────────────────────────────────────────────────────────


-- ── 1. Conversations (unchanged from V1) ─────────────────────────────────────
create table if not exists conversations (
    id            bigserial       primary key,
    chat_id       text            not null,
    username      text,
    user_message  text            not null,
    bot_reply     text            not null,
    model         text            not null default 'claude-sonnet-4-20250514',
    latency_ms    integer,
    created_at    timestamptz     not null default now()
);

create index if not exists idx_conversations_chat_id
    on conversations (chat_id, created_at desc);


-- ── 2. Products (constraint source-of-truth) ──────────────────────────────────
-- The bot checks this table before generating any quotation.
-- Never quote a product outside its application_scope.
create table if not exists products (
    id                      serial          primary key,
    product_code            text            not null unique,
    product_name            text            not null,
    description             text,
    unit_price              numeric(12, 2)  not null,
    unit                    text            not null default 'sqm',
    application_scope       text[]          not null,
    disallowed_applications text[]          not null default '{}',
    constraint_note         text,
    is_active               boolean         not null default true,
    created_at              timestamptz     not null default now()
);

-- Seed data
insert into products (
    product_code, product_name, description,
    unit_price, unit,
    application_scope, disallowed_applications, constraint_note
) values
(
    'WTZ-1800',
    'WaterTreat Above-Waterline Sealant',
    'High-performance polyurethane sealant for above-waterline joints. NOT rated for continuous immersion.',
    1450.00, 'ltr',
    ARRAY['above-waterline', 'parapet', 'facade', 'expansion-joint', 'roof', 'terrace', 'balcony'],
    ARRAY['submerged', 'underwater', 'pool', 'sump', 'tank', 'below-waterline', 'hydrostatic', 'immersion', 'wet-area-floor'],
    'WTZ-1800 is rated for ABOVE-WATERLINE applications only. Use WTZ-3400S for submerged pool joints.'
),
(
    'WTZ-3400S',
    'WaterTreat Submerged Joint Sealant',
    'Two-component polysulphide sealant rated for continuous immersion, hydrostatic pressure, and pool/tank joints.',
    2800.00, 'ltr',
    ARRAY['submerged', 'pool', 'sump', 'tank', 'below-waterline', 'hydrostatic', 'underwater'],
    ARRAY[],
    NULL
),
(
    'WTZ-550C',
    'WaterTreat Cementitious Coating',
    'Rigid cementitious waterproofing for basement walls, retaining walls, and below-grade structures.',
    620.00, 'kg',
    ARRAY['basement', 'retaining-wall', 'below-grade', 'foundation', 'plinth'],
    ARRAY['roof', 'terrace', 'expansion-joint'],
    'WTZ-550C is not flexible — do not use on roofs, terraces, or expansion joints.'
)
on conflict (product_code) do nothing;


-- ── 3. Bot Audit Log ──────────────────────────────────────────────────────────
-- Every bot action is logged here BEFORE a response is sent.
-- action_type: LLM_RESPONSE | QUOTE_GENERATED | GUARDRAIL_TRIGGERED |
--              PRODUCT_NOT_FOUND | ESCALATED | HIGH_VALUE_ESCALATION |
--              COMPLIANCE_QUERY | ERROR
create table if not exists bot_audit_log (
    id              bigserial       primary key,
    chat_id         text            not null,
    username        text,
    action_type     text            not null,
    input_text      text            not null,
    output_text     text,
    warnings        text[],
    product_code    text,
    quote_value     numeric(12, 2),
    escalated       boolean         not null default false,
    created_at      timestamptz     not null default now()
);

create index if not exists idx_audit_chat_id
    on bot_audit_log (chat_id, created_at desc);

create index if not exists idx_audit_action_type
    on bot_audit_log (action_type, created_at desc);