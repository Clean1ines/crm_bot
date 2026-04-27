# CRM Bot Runtime

CRM Bot Runtime is a multi-tenant customer communication backend for Telegram-based customer support, CRM-style project administration, manager handoff, event persistence, and LLM/RAG-assisted responses.

The backend is built around FastAPI, PostgreSQL with pgvector, Redis, Telegram webhooks, and a typed agent runtime. The frontend lives in `frontend/` and consumes the generated OpenAPI contract.

## What this project does

The system provides:

* Telegram client bot webhook handling for customer conversations.
* Telegram platform/admin and manager flows.
* FastAPI HTTP API for frontend and integrations.
* Multi-project administration, memberships, bot token storage, and webhook secrets.
* Customer/client profile and thread lifecycle persistence.
* Knowledge document ingestion, chunking, embeddings, and RAG search.
* LLM-backed intent extraction, query expansion, and response generation.
* Queue-based background jobs for notifications, metrics, and retries.
* Event timeline persistence for auditability.
* Architecture tests that protect runtime boundaries.

## Repository layout

```text
src/
  domain/          Pure domain contracts, runtime state models, policies, value parsing
  application/     Use-case services, DTOs, orchestration ports
  infrastructure/  DB, Redis, queue, LLM, embedding, repository adapters
  interfaces/      FastAPI and Telegram entrypoints
  agent/           LangGraph runtime adapter and graph nodes
  tools/           Tool registry and builtin tool implementations

migrations/        SQL migrations and the migration runner
frontend/          Frontend application and generated OpenAPI client inputs
tests/             Unit, integration, architecture, and runtime contract tests
scripts/           Audit, generation, maintenance, and local utility scripts
```

## Main runtime flow

A typical client conversation looks like this:

1. Telegram sends a webhook to the HTTP interface layer.
2. The conversation orchestrator loads project, thread, memory, and knowledge context.
3. The agent graph runs runtime nodes:

   * load state
   * rules check
   * intent extraction
   * policy decision
   * knowledge search
   * tool execution
   * escalation
   * response generation
   * response delivery
   * persistence
4. The response is delivered to Telegram or escalated to a manager.
5. Events, messages, runtime state, and analytics side effects are persisted where appropriate.

The graph contract lives in `src/domain/runtime/graph_contract.py`.

The concrete LangGraph adapter lives in `src/agent/graph.py`.

## Architecture boundaries

The project is intentionally layered:

* `domain/` must stay pure and must not depend on FastAPI, DB clients, Redis, Telegram, or LLM runtime packages.
* `application/` coordinates use cases through DTOs and ports.
* `infrastructure/` implements repositories, queue workers, Redis, LLM, embedding, and external adapters.
* `interfaces/` owns HTTP and Telegram request handling.
* `agent/` wires the runtime graph and graph nodes.
* Runtime wiring happens at composition boundaries.

Boundary checks are enforced by tests under `tests/architecture/`.

## Failure behavior

The runtime is expected to degrade deterministically:

* If Groq/LLM calls fail, graph nodes use safe fallbacks or user-safe error text.
* If RAG finds no chunks, prompts receive an explicit no-knowledge marker.
* If Telegram delivery fails, operational details are logged internally.
* If queue jobs fail transiently, retry policy handles retries.
* If a queue payload is malformed, it should fail permanently instead of retrying forever.
* If a PDF or document is empty or unreadable, ingestion should return a safe user-facing failure.
* Duplicate webhook handling should avoid duplicate irreversible side effects where stable IDs are available.

## Observability and logging rules

The codebase uses structured logging and request correlation.

Logging should include stable operational identifiers where useful:

* project ID
* thread ID
* event type
* job type
* error type

Logging must not include raw secrets:

* bot tokens
* authorization headers
* webhook secrets
* decrypted credentials
* passwords
* raw private user data unless explicitly needed and safe

External errors should remain safe for users. Detailed operational errors belong in internal logs.

## Security triage

Security findings should be triaged, not silently ignored.

The repository includes:

* `.bandit`
* security audit scripts under `scripts/`
* generated local audit output under `reports/`

## Requirements

### Backend

* Python 3.12+
* PostgreSQL with pgvector
* Redis
* Telegram bot tokens
* Groq API key for LLM-backed runtime behavior

### Frontend

* Node.js
* npm

Python runtime dependencies are pinned in `requirements.txt`.

Development and test dependencies are listed in `requirements-dev.txt`.

## Environment

Start from the example file:

```bash
cp .env.example .env
```

Important environment variables used by the backend include:

```text
DATABASE_URL
REDIS_URL
GROQ_API_KEY
GROQ_MODEL
DEFAULT_MODEL
ADMIN_BOT_TOKEN
ADMIN_CHAT_ID
PLATFORM_WEBHOOK_SECRET
BOOTSTRAP_PLATFORM_OWNER
PLATFORM_OWNER_TELEGRAM_ID
GOOGLE_CLIENT_ID
VITE_GOOGLE_CLIENT_ID
JWT_SECRET_KEY
TOKEN_ENCRYPTION_KEY
RENDER_EXTERNAL_URL
PUBLIC_URL
FRONTEND_URL
```

Project-specific client and manager bot tokens are stored through project configuration and repository flows, not as separate global `CLIENT_BOT_TOKEN` or `MANAGER_BOT_TOKEN` variables.

Never commit real `.env`, `.env.test`, `.env.prod`, bot tokens, webhook secrets, JWT secrets, or encryption keys.

## Local setup

Create and activate a virtual environment:

```bash
python -m venv venv
. venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Start local infrastructure:

```bash
docker compose up -d db_dev db_test redis_test
```

The current `docker-compose.yml` starts infrastructure only:

* `db_dev`
* `db_test`
* `redis_test`

It does not start the FastAPI application container.

Apply database migrations:

```bash
python migrations/run_all.py
```

Important: the migration runner scans allowed env files in the project root: `.env`, `.env.test`, and `.env.prod`. For `.env.prod` it asks for explicit confirmation before applying migrations.

Run the backend locally:

```bash
uvicorn src.interfaces.http.app:app --host 0.0.0.0 --port 8000 --reload
```

## Make targets

The repository includes a `Makefile` with these targets:

```bash
make install
make infra-up
make migrate
make format
make lint
make typecheck
make test
make check
make run
make openapi
```

## Quality gate

Before committing backend changes, run:

```bash
ruff format src tests
ruff check src tests
mypy src
pytest -q
```

## OpenAPI

Generate the backend OpenAPI schema with:

```bash
python scripts/generate_openapi.py
```

The frontend consumes the generated API contract.

## Frontend

The frontend lives in `frontend/`.

Typical local commands:

```bash
cd frontend
npm install
npm run dev
```

## Docker

Build the backend image:

```bash
docker build -t crm-bot-runtime .
```

The current `Dockerfile` uses:

* `python:3.12-slim`
* `supervisord`
* application source copied from `src/`, `migrations/`, and `scripts/`

## Migrations

SQL migrations live in `migrations/`.

The migration runner is:

```text
migrations/run_all.py
```

It creates and uses `public.schema_migrations` to track applied SQL files and applies all `*.sql` migrations in sorted order for each allowed environment file.

## Testing

The project includes a large automated test suite covering:

* agent nodes
* API routes
* application services
* database repositories
* domain logic
* infrastructure contracts
* Telegram interface behavior
* architecture boundary checks

Run the full suite with:

```bash
pytest -q
```
