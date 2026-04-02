-- =============================================================================
-- Genotek Sales Support Bot -- Supabase Schema
-- =============================================================================
-- Run this in Supabase SQL Editor to set up all required tables.
-- Requires: pgvector extension (for embeddings)
-- =============================================================================

-- Enable pgvector for embedding storage
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- 1. PRODUCTS TABLE
-- Stores product catalog with application constraints for guardrail checks.
-- =============================================================================
CREATE TABLE IF NOT EXISTS products (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    product_code    TEXT NOT NULL UNIQUE,
    product_name    TEXT NOT NULL,
    product_family  TEXT NOT NULL,           -- e.g., 'WTZ', 'EJ', 'FB'
    description     TEXT,
    application_constraints JSONB NOT NULL DEFAULT '{}',
    -- Example: {"environment": "above-waterline", "max_movement_mm": 50,
    --           "fire_rated": false, "indoor_only": false}
    supplier_id     TEXT,                    -- supplier reference
    supplier_name   TEXT,
    regions         TEXT[] DEFAULT '{}',     -- applicable regions
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Seed critical product data for guardrail testing
INSERT INTO products (product_code, product_name, product_family, description, application_constraints, supplier_name, regions)
VALUES
    ('WTZ-1800', 'WTZ-1800 Expansion Joint Cover', 'WTZ',
     'Wall/ceiling expansion joint cover for above-waterline applications',
     '{"environment": "above-waterline", "prohibited_environments": ["submerged", "underwater", "below-waterline", "pool-submerged"], "max_movement_mm": 50, "fire_rated": false}',
     'Ankara Factory', ARRAY['UAE', 'KSA', 'India', 'SEA']),

    ('WTZ-2400', 'WTZ-2400 Expansion Joint Cover (Waterproof)', 'WTZ',
     'Expansion joint cover rated for submerged and below-waterline applications',
     '{"environment": "all-weather", "submersible": true, "waterproof": true, "max_movement_mm": 75, "fire_rated": false}',
     'Ankara Factory', ARRAY['UAE', 'KSA', 'India', 'SEA']),

    ('WTZ-1200', 'WTZ-1200 Standard Expansion Joint Cover', 'WTZ',
     'Standard expansion joint cover for interior/exterior above-waterline',
     '{"environment": "above-waterline", "prohibited_environments": ["submerged", "underwater", "below-waterline"], "max_movement_mm": 30, "fire_rated": false}',
     'Ankara Factory', ARRAY['UAE', 'KSA', 'India', 'SEA']),

    ('EJ-FB100', 'Fire Barrier Expansion Joint', 'FB',
     'Fire-rated expansion joint barrier, 2-hour rating',
     '{"environment": "interior", "fire_rated": true, "fire_rating_hours": 2, "prohibited_environments": ["exterior-exposed"]}',
     'EZS Slovenia', ARRAY['UAE', 'KSA']),

    ('EJ-AL300', 'Aluminum Profile Expansion Joint', 'EJ',
     'Custom aluminum expansion joint profile',
     '{"environment": "all-weather", "material": "aluminum", "custom_die_required": true, "lead_time_note": "75-85 days for custom dies"}',
     'RY Extrusion', ARRAY['UAE', 'KSA', 'India', 'SEA']),

    ('EJ-RB200', 'EPDM Rubber Profile Joint', 'EJ',
     'Rubber profile expansion joint cover',
     '{"environment": "above-waterline", "material": "EPDM", "prohibited_environments": ["submerged"]}',
     'MPP', ARRAY['UAE', 'KSA', 'India']),

    ('WTZ-3000', 'WTZ-3000 Heavy Duty Floor Joint', 'WTZ',
     'Heavy-duty floor expansion joint for vehicle traffic',
     '{"environment": "floor", "traffic_rated": true, "max_load_kg": 5000, "prohibited_environments": ["wall-mount", "ceiling"]}',
     'Ankara Factory', ARRAY['UAE', 'KSA', 'India', 'SEA']),

    ('FB-SS304', 'Stainless Steel Fire Barrier', 'FB',
     'SS304 stainless steel fire barrier system',
     '{"environment": "interior", "fire_rated": true, "material": "SS304", "fire_rating_hours": 4}',
     'Gous', ARRAY['UAE', 'KSA'])
ON CONFLICT (product_code) DO NOTHING;


-- =============================================================================
-- 2. CONVERSATIONS TABLE
-- Stores every conversation turn for Open Brain memory.
-- =============================================================================
CREATE TABLE IF NOT EXISTS conversations (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id         BIGINT NOT NULL,         -- Telegram user ID
    username        TEXT,                     -- Telegram username
    session_id      TEXT NOT NULL,            -- Groups turns in a session
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL CHECK (content != ''),
    model_used      TEXT,                     -- e.g., 'claude-3-5-haiku', 'claude-3-5-sonnet'
    tokens_input    INTEGER,
    tokens_output   INTEGER,
    cost_estimate   NUMERIC(10, 6),          -- estimated cost in USD
    metadata        JSONB DEFAULT '{}',       -- additional context
    embedding       vector(1536),             -- for semantic search via pgvector
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast user session lookups
CREATE INDEX IF NOT EXISTS idx_conversations_user_session
    ON conversations (user_id, session_id, created_at DESC);

-- Index for embedding similarity search
CREATE INDEX IF NOT EXISTS idx_conversations_embedding
    ON conversations USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);


-- =============================================================================
-- 3. BOT_AUDIT_LOG TABLE
-- Every bot action logged with full input/output and warnings.
-- =============================================================================
CREATE TABLE IF NOT EXISTS bot_audit_log (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    timestamp       TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    user_id         BIGINT,                  -- Telegram user ID (null for system actions)
    username        TEXT,
    session_id      TEXT,
    action_type     TEXT NOT NULL CHECK (action_type IN (
        'MESSAGE',
        'QUOTE_ROUTE',
        'PRODUCT_CHECK',
        'PRICING_ESCALATION',
        'FOLLOWUP_TRIGGER',
        'PRODUCT_CONSTRAINT_VIOLATION',
        'DISCOUNT_ESCALATION',
        'MODEL_ROUTE',
        'ERROR'
    )),
    input_text      TEXT,
    output_text     TEXT,
    warnings        JSONB DEFAULT '[]'::JSONB,
    model_used      TEXT,
    latency_ms      INTEGER,                 -- response time in milliseconds
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Index for audit queries
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp
    ON bot_audit_log (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_audit_log_user
    ON bot_audit_log (user_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_audit_log_action_type
    ON bot_audit_log (action_type, timestamp DESC);


-- =============================================================================
-- 4. SUPPLIERS TABLE
-- Verified supplier data from 18-month email audit.
-- =============================================================================
CREATE TABLE IF NOT EXISTS suppliers (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    products        TEXT[],
    avg_lead_days   INTEGER,
    payment_status  TEXT DEFAULT 'current',
    known_issues    TEXT,
    regions         TEXT[],
    contact_email   TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Seed verified supplier data
INSERT INTO suppliers (name, products, avg_lead_days, payment_status, known_issues, regions)
VALUES
    ('Ankara Factory', ARRAY['WTZ standard profiles', 'Custom items'], 29,
     'current', 'SABER certification gap for KSA', ARRAY['UAE', 'KSA', 'SEA']),
    ('RY Extrusion', ARRAY['Aluminum profiles', 'Custom dies'], 80,
     'current', 'Force majeure history. 75-85 day die lead times.', ARRAY['UAE', 'KSA', 'India', 'SEA']),
    ('MPP', ARRAY['Rubber profiles', 'EPDM'], NULL,
     'overdue', '1+ month overdue payments. OSV registration blocking.', ARRAY['UAE', 'KSA', 'India']),
    ('EZS Slovenia', ARRAY['Fire barriers'], NULL,
     'current', 'Specialist -- limited capacity', ARRAY['UAE', 'KSA']),
    ('Gous', ARRAY['SS304 stainless steel'], NULL,
     'current', NULL, ARRAY['UAE', 'KSA']),
    ('Martin', ARRAY['Fire barriers'], NULL,
     'current', NULL, ARRAY['UAE', 'KSA']),
    ('Morgan', ARRAY['Fire rope'], NULL,
     'current', NULL, ARRAY['UAE', 'KSA']),
    ('Suraksha Sync', ARRAY['Fire barriers (India)'], NULL,
     'current', 'AD code registration pending (GCC unlock)', ARRAY['India'])
ON CONFLICT (name) DO NOTHING;


-- =============================================================================
-- 5. PRICING_RULES TABLE
-- Escalation rules for the pricing router.
-- =============================================================================
CREATE TABLE IF NOT EXISTS pricing_rules (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    region          TEXT NOT NULL,
    condition_desc  TEXT NOT NULL,
    route_to        TEXT NOT NULL,            -- person/role
    authority_level TEXT NOT NULL,
    is_verified     BOOLEAN DEFAULT FALSE,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO pricing_rules (region, condition_desc, route_to, authority_level, is_verified, notes)
VALUES
    ('UAE', 'Value < AED 100/LM', 'Shylesh', 'auto-approve-small', TRUE,
     'Shylesh autonomous pricing for small UAE items'),
    ('KSA', 'Value > SAR 500K', 'Bijoy', 'large-deal', TRUE,
     'All large KSA deals require Bijoy'),
    ('India', 'All pricing', 'Niranjan', 'pidilite-channel', TRUE,
     'India pricing via Pidilite channel'),
    ('ANY', 'Discount > 15%', 'Bijoy', 'discount-authority', TRUE,
     'Discounts above 15% always require Bijoy -- no exceptions'),
    ('Turkey', 'Custom items', 'Ankara Factory', 'factory-baseline', TRUE,
     '29-day baseline for custom Turkey items'),
    ('International', 'All other regions', 'Bijoy', 'strategic', TRUE,
     'All international/non-standard pricing goes to Bijoy')
ON CONFLICT DO NOTHING;


-- =============================================================================
-- 6. Helper function: search conversations by embedding similarity
-- =============================================================================
CREATE OR REPLACE FUNCTION match_conversations(
    query_embedding vector(1536),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 10
)
RETURNS TABLE (
    id UUID,
    user_id BIGINT,
    role TEXT,
    content TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.user_id,
        c.role,
        c.content,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM conversations c
    WHERE 1 - (c.embedding <=> query_embedding) > match_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
