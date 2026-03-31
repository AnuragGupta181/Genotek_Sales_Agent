# Claude Telegram Bot

A Telegram bot that sends messages to the Claude API and logs every conversation turn to a Supabase table.

Built as a practical task using `python-telegram-bot`, `anthropic`, and `supabase-py`.

---

## Features

- Multi-turn conversation with context (last 10 turns kept in-session)
- `/clear` to reset conversation history
- Every message + reply logged to Supabase with `chat_id`, `username`, `latency_ms`, and `timestamp`
- Clean async architecture using `python-telegram-bot v21`

---

## Stack

| Layer | Tool |
|---|---|
| Bot framework | `python-telegram-bot` v21 |
| LLM | Claude (`claude-sonnet-4-20250514`) via Anthropic SDK |
| Database | Supabase (Postgres) |
| Runtime | Python 3.12 |

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/claude-telegram-bot
cd claude-telegram-bot
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Fill in `.env`:

```
TELEGRAM_BOT_TOKEN=       # From @BotFather on Telegram
ANTHROPIC_API_KEY=        # From console.anthropic.com
SUPABASE_URL=             # From Supabase project settings → API
SUPABASE_SERVICE_ROLE_KEY= # From Supabase project settings → API (service_role)
```

### 4. Create the Supabase table

Open your Supabase project → **SQL Editor** → paste and run `schema.sql`:

```sql
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
```

### 5. Run the bot

```bash
python bot.py
```

You should see:
```
Bot is running… (polling)
```

Open Telegram, find your bot, and send a message.

---

## Supabase Table Schema

| Column | Type | Description |
|---|---|---|
| `id` | bigserial | Auto-increment primary key |
| `chat_id` | text | Telegram chat/user ID |
| `username` | text | @handle or full name |
| `user_message` | text | What the user sent |
| `bot_reply` | text | Claude's response |
| `model` | text | Claude model used |
| `latency_ms` | integer | Round-trip time to Claude API (ms) |
| `created_at` | timestamptz | UTC timestamp |

---

## Docker (optional)

```bash
docker build -t claude-telegram-bot .
docker run -d --env-file .env --name claude-bot claude-telegram-bot
```

---

## Issues hit during development

1. **`python-telegram-bot` async model** — v21 is fully async. The old `Updater` pattern is gone; everything uses `ApplicationBuilder`. Took a quick read of the migration guide to get it right.

2. **Supabase `service_role` key vs `anon` key** — The `anon` key respects RLS policies. Since the bot writes server-side with no user auth, using `service_role` key bypasses RLS cleanly. Don't expose this key on the client side.

3. **Claude message history format** — The Anthropic SDK requires alternating `user`/`assistant` roles. If you accidentally append two user turns in a row (e.g., on a retry), Claude throws a validation error. Handled by always appending the assistant reply before the next user message.

4. **`latency_ms` tracking** — Measured as wall-clock time around the `claude_client.messages.create()` call. Includes network round-trip to Anthropic, not just model inference.

---

## Project structure

```
claude-telegram-bot/
├── bot.py            # Main bot logic
├── schema.sql        # Supabase table definition
├── requirements.txt
├── Dockerfile
├── .env.example
├── .gitignore
└── README.md
```
