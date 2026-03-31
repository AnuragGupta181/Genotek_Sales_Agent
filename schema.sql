-- ─────────────────────────────────────────────────────────────────────────────
-- Supabase schema for claude-telegram-bot
-- Run this once in the Supabase SQL Editor (Dashboard → SQL Editor → New query)
-- ─────────────────────────────────────────────────────────────────────────────

create table if not exists conversations (
    id            bigserial       primary key,

    -- Telegram identifiers
    chat_id       text            not null,          -- Telegram chat/user ID
    username      text,                               -- @handle or full name

    -- The actual messages
    user_message  text            not null,
    bot_reply     text            not null,

    -- Metadata
    model         text            not null default 'claude-sonnet-4-20250514',
    latency_ms    integer,                            -- round-trip to Claude in ms
    created_at    timestamptz     not null default now()
);

-- Index for fast per-user history lookups
create index if not exists idx_conversations_chat_id
    on conversations (chat_id, created_at desc);

-- Optional: enable Row Level Security if you expose the table to the frontend
-- alter table conversations enable row level security;
