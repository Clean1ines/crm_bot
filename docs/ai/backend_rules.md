# Backend Rules

## Recon before backend changes

Before editing backend code, inspect:
- target file;
- neighboring files;
- call sites;
- ports and interfaces;
- DTO/domain contracts;
- related tests;
- architecture tests;
- existing error handling;
- existing logging style;
- runtime dependencies;
- migration impact if DB is involved.

Do not patch based only on search output.

## Layer rules

### Domain

Allowed:
- pure functions;
- value parsing;
- dataclasses;
- TypedDict contracts;
- policy decisions;
- serialization helpers without external side effects.

Forbidden:
- FastAPI;
- asyncpg;
- Redis;
- Telegram SDK;
- LLM SDK;
- filesystem IO except narrowly justified pure parsing;
- environment reads;
- network calls.

### Application

Allowed:
- services;
- use-case orchestration;
- ports;
- DTO conversion;
- domain policy usage.

Forbidden:
- transport-specific request handling;
- direct Telegram API calls;
- direct DB client usage when a port/repository exists;
- infrastructure SDK details.

### Infrastructure

Allowed:
- repositories;
- DB queries;
- Redis;
- queue;
- LLM adapter code;
- embeddings;
- external integrations.

Required:
- parameterized SQL;
- masked logging;
- bounded operations;
- graceful failure behavior where appropriate.

### Interfaces

Allowed:
- FastAPI routes;
- Telegram update handling;
- request parsing;
- response formatting;
- dependency resolution through composition.

Required:
- delegate business logic;
- validate inputs;
- avoid large business workflows in handlers.

### Agent

Allowed:
- graph nodes;
- runtime adapter logic;
- prompt assembly;
- typed state patching;
- lazy LLM imports.

Required:
- no untyped node contracts;
- no heavy import side effects at plain app import;
- deterministic fallbacks;
- focused tests for node behavior.

## Typing

Do not add `Any` by default.

Use:
- `Protocol` for dependencies;
- `TypedDict` for structured mappings;
- `Mapping[str, object]` for JSON-like read-only data;
- dataclasses for internal domain results;
- explicit return types;
- narrow helper functions.

If a function receives dynamic external data:
1. keep it at the boundary;
2. validate it;
3. convert it into typed structures;
4. pass typed structures deeper.

## Complexity

Do not increase complexity casually.

If logic grows:
- extract pure helpers;
- use mapping tables;
- split validation from side effects;
- split parsing from persistence;
- split policy from transport.

Do not mix:
- DB IO and policy decision;
- LLM parsing and persistence;
- Telegram formatting and domain logic;
- error handling and unrelated state mutation.

## Async

For async paths:
- avoid blocking IO;
- avoid sync network calls;
- avoid repeated DB calls in loops when a batched query is possible;
- preserve cancellation-friendly behavior;
- do not hide async failures.

## Database

For DB changes:
- inspect existing migrations and repository patterns;
- use parameterized SQL;
- avoid unsafe string interpolation;
- preserve project/client scoping;
- add migrations only when schema changes are required;
- make migrations idempotent where project convention supports it;
- consider backfill behavior and existing production data.

## LLM/RAG

For LLM and RAG changes:
- keep prompts modular and testable;
- keep structured LLM output validated;
- do not let the LLM write persistent memory directly;
- use deterministic gates before persistence;
- preserve empty-RAG fallback behavior;
- avoid extra LLM calls unless justified;
- keep prompt context compact;
- do not expose hidden reasoning or internal scoring to users.

## Memory

For memory changes:
- inspect existing memory repository, load-state, persist, dialog_state, prompt builder, and state contracts;
- preserve schema compatibility if possible;
- validate memory writes deterministically;
- distinguish durable facts from transient dialogue state;
- avoid storing raw sensitive text unnecessarily;
- avoid overwriting stable user facts from weak evidence;
- prefer explicit memory types and keys;
- keep write gates narrow and testable.

## Telegram/webhooks

For Telegram changes:
- inspect current route ownership;
- preserve idempotency;
- handle duplicate updates safely;
- validate webhook secrets correctly;
- do not confuse bot token with webhook secret;
- avoid logging full tokens;
- keep platform, client, and manager bot routes distinct unless compatibility is explicitly required.

## Backend validation

Use focused checks first:
- relevant pytest files;
- py_compile for touched files if useful;
- mypy for touched modules or full `mypy src`;
- ruff check/format;
- architecture tests if boundaries may be affected;
- full pytest for cross-cutting changes.

Do not weaken tests to pass.
