# Project Contract

This project is a CRM Telegram bot and CRM panel with a typed backend, LLM/RAG runtime, Telegram integrations, PostgreSQL, Redis, and a frontend application.

The codebase is expected to remain production-grade.

## Backend stack

- Python 3.12
- FastAPI
- PostgreSQL
- pgvector
- Redis
- Telegram webhooks
- LLM/RAG runtime
- Typed agent runtime
- SQL migrations
- Layered architecture

## Frontend stack

- Frontend lives under `frontend/`
- React/Vite/TypeScript unless the repository shows otherwise
- Generated OpenAPI client may be present
- Existing design system must be inferred from current files before frontend edits

## Repository layers

- `src/domain`: pure domain contracts, runtime state, policy, value parsing
- `src/application`: use cases, DTOs, orchestration ports
- `src/infrastructure`: DB, Redis, queue, LLM, embedding, repository adapters
- `src/interfaces`: FastAPI and Telegram entrypoints
- `src/agent`: graph adapter and graph nodes
- `src/tools`: tool registry and builtin tool implementations
- `migrations`: SQL migrations
- `frontend`: frontend app
- `tests`: unit, integration, architecture, runtime contract tests

## Runtime flow

Expected high-level runtime flow:

1. Telegram sends webhook to HTTP interface.
2. Conversation orchestrator loads project, thread, memory, knowledge context.
3. Agent graph runs runtime nodes:
   - load state;
   - rules check;
   - intent extraction;
   - policy decision;
   - knowledge search;
   - tool execution;
   - escalation;
   - response generation;
   - response delivery;
   - persistence.
4. Response is delivered or escalated.
5. Events, messages, runtime state, analytics, and memory side effects are persisted.

Do not assume this flow blindly. Verify actual code before changes.

## Architectural expectation

The project should maintain clean boundaries:
- domain stays pure;
- application coordinates;
- infrastructure implements external adapters;
- interfaces own transport;
- agent owns graph/runtime adaptation;
- composition boundaries wire dependencies.

Architecture tests are part of the contract. Do not bypass them.
