# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

bol-api is a large language model API relay station that proxies requests to multiple LLM providers (OpenAI, Anthropic, custom endpoints) with unified API Key authentication and usage tracking.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run production server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Architecture

### Core Flow
1. **Request → AuthMiddleware** validates Bearer token against SHA256 hash in database
2. **ChannelManager** selects appropriate upstream channel based on model matching + priority + weight
3. **Provider** (OpenAI/Anthropic/Custom) formats request and forwards to upstream API
4. **UsageRecorder** asynchronously logs token usage and estimated cost

### Channel Scheduling Strategy (`app/channels/manager.py`)
- Model matching: exact match or wildcard prefix (`gpt-4*` matches `gpt-4-turbo`)
- Priority grouping: higher priority channels are selected first
- Weighted random: within the highest priority group, channels are selected by weighted random distribution
- Empty models list means the channel supports all models

### Provider Protocol Switch (`app/providers/custom.py`)
CustomProvider supports both OpenAI and Anthropic API formats via `api_protocol` field:
- `openai`: uses `/v1/chat/completions` endpoint, Bearer auth, `prompt_tokens/completion_tokens`
- `anthropic`: uses `/v1/messages` endpoint, `x-api-key` header, `input_tokens/output_tokens`

### Key Patterns

**API Key Storage**: Raw keys are hashed with SHA256 for validation. The encrypted_key field stores the original key for admin reveal functionality. Key prefix (e.g., `bol-abc...xyz`) is stored for display.

**Async Queue Pattern**: UsageRecorder uses an asyncio.Queue with background task for non-blocking logging. Initialized in lifespan, processes queue continuously.

**HTTP Client**: Singleton httpx.AsyncClient shared across all requests, closed on app shutdown.

**Auth Middleware**: Returns JSONResponse directly for auth errors (not HTTPException which causes 500 in middleware). Public paths are split into PUBLIC_EXACT (exact match like `/`) and PUBLIC_PREFIXES (prefix match like `/admin`).

### Database Models (`app/db/models.py`)
- `APIKey`: user keys with hash, encrypted storage, prefix display
- `Channel`: upstream provider config with models list (JSON), priority/weight for scheduling
- `UsageLog`: tracking records with tokens, cost, latency, status

### Web Admin Interface (`app/routers/admin.py`)
Single-page HTML admin at `/admin` with password protection. Features:
- API Key management with show/copy functionality
- Channel management with edit, test (shows latency)
- Usage statistics dashboard

## Environment Variables

Configure in `.env`:
- `ADMIN_PASSWORD`: admin interface password (default: admin123)
- `DATABASE_URL`: SQLite path (default: sqlite+aiosqlite:///./data/bol_api.db)
- `ENCRYPTION_KEY`: key encryption secret

## API Endpoints

- `/v1/chat/completions` - OpenAI format chat API (Bearer token required)
- `/v1/messages` - Anthropic format messages API (Bearer token required)
- `/admin` - Web management interface
- `/stats/summary` - Usage statistics summary
- `/stats/logs` - Detailed usage logs