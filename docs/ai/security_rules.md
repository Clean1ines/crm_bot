# Security Rules

Security is part of code quality. Do not treat it as an optional final scan.

## Secrets

Never print or commit:
- database URLs;
- Telegram bot tokens;
- API keys;
- webhook secrets;
- encryption keys;
- JWT secrets;
- OAuth secrets;
- provider credentials.

Mask secrets in logs, diagnostics, comments, fixtures, generated examples, and error messages.

If a real secret appears in user input or existing local output, do not repeat it. Treat it as exposed and recommend rotation only when a user-facing summary is requested.

## Logging

Logs must be useful and safe.

Do:
- use structured logging;
- include stable identifiers where useful;
- mask sensitive values;
- log failure class and safe context.

Do not:
- log full tokens;
- log raw auth headers;
- log full database URLs;
- log full webhook secrets;
- log raw personal data unless necessary and safe;
- log full LLM prompts if they may contain secrets or private user data.

## External services

Assume external services fail:
- Telegram;
- LLM providers;
- embeddings;
- Redis;
- PostgreSQL;
- HTTP APIs;
- file extraction/parsing.

Required behavior:
- safe failure;
- deterministic fallback where possible;
- observable errors;
- no corrupted state;
- no fake success unless explicitly intended and logged.

## SQL

Use parameterized SQL.

Dynamic SQL is acceptable only when:
- dynamic parts are from allowlisted constants;
- values remain parameterized;
- project/client scoping is preserved;
- tests cover the behavior.

## Webhooks

For webhooks:
- validate secrets correctly;
- keep bot tokens separate from webhook secrets;
- handle duplicate delivery safely;
- avoid leaking request bodies;
- avoid returning misleading success for invalid routing unless explicitly required for compatibility.

## LLM safety

For LLM outputs:
- validate structured output;
- never persist untrusted LLM output directly as durable truth;
- apply deterministic gates;
- preserve RAG factuality constraints;
- do not invent facts;
- do not expose internal analysis, scores, or policies to end users.

## Memory safety

Memory writes must be conservative.

Do not store:
- unnecessary raw sensitive messages;
- threats or self-harm text as reusable personalization;
- payment data beyond safe references;
- secrets;
- unsupported inferred facts.

Prefer:
- short normalized facts;
- confidence-aware write gates;
- explicit memory type/key;
- deterministic extraction rules;
- human-review path for risky cases.
