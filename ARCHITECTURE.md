# Architecture Specification

This document is the source of truth for the platform refactor. It exists so a
human or AI implementer can continue the migration without reintroducing the old
domain model.

## Product Shape

The system is a multi-tenant SaaS platform for AI assistants, not a single
Telegram bot with a dashboard.

The platform is split into four planes:

- Control plane: project creation, project configuration, members, auth methods,
  knowledge, channels, integrations, limits, analytics overview.
- Project plane: contacts, threads, messages, tasks, manager workbench,
  escalations, project-specific runtime operations.
- Identity plane: platform users and auth providers.
- Runtime plane: assistant orchestration, prompt assembly, RAG, tools, memory,
  model selection, rate limits and event emission.

## Non-Negotiable Domain Invariants

- `users` are platform people.
- `clients` are project-scoped business contacts/end customers.
- The same physical person may be both a platform `user` and a project `client`.
- That bridge is `clients.user_id`; it is optional and must not make `clients`
  an auth table.
- `projects.user_id` is the canonical project owner reference.
- `projects.owner_id` must not be used as runtime truth.
- `users.project_id` must not exist in domain logic.
- Project roles live only in `project_members(project_id, user_id, role)`.
- Platform administration lives only in `users.is_platform_admin`.
- Telegram chat ids are transport identifiers, not role truth.
- Manual thread assignment is `threads.manager_user_id`; `manager_chat_id` is
  only a legacy Telegram transport bridge while compatibility remains.
- Platform bot is a control-plane surface.
- Web panel is a control-plane surface.
- Client bot, manager bot and web widget are project-plane surfaces.
- Templates are not part of the product unless explicitly reintroduced.
- Runtime must consume explicit project configuration instead of hidden globals.

## Identity And Auth

Canonical tables:

- `users`: platform identity/profile fields.
- `auth_identities`: linked auth providers for one platform user.
- `user_credentials`: password hash for email/password login.

Supported providers:

- Telegram widget/bot login.
- Email/password.
- Google Identity Services / OAuth ID token.

Rules:

- One physical platform account equals one `users.id`.
- Multiple login methods link to one `users.id`.
- Google must be linked from an already authenticated session by default.
- Email linking for Telegram/Google users requires setting a password.
- `users.email` is allowed because email is platform identity/auth data.
- CRM-only data such as company/phone belongs to `clients`, not `users`.
- Platform owner bootstrap may create/update one Telegram-linked `user` with
  `is_platform_admin=true`; it must not create a project or project membership.
- Backend validates Google ID token audience with `GOOGLE_CLIENT_ID`.
- Frontend renders Google Identity Services using `VITE_GOOGLE_CLIENT_ID`; manual
  ID token inputs are temporary dev bridges, not the primary product flow.

## Project Roles

Global role:

- `users.is_platform_admin`: platform operator.

Bootstrap:

- On startup, `BOOTSTRAP_PLATFORM_OWNER=true` ensures the configured
  `PLATFORM_OWNER_TELEGRAM_ID` exists as a Telegram-linked platform user with
  `users.is_platform_admin=true`.
- If `PLATFORM_OWNER_TELEGRAM_ID` is not configured, bootstrap falls back to
  `ADMIN_CHAT_ID`.
- This is the only intended automatic grant for global platform ownership.

Project roles:

- `owner`: full project control.
- `admin`: project administration.
- `manager`: dialogs, tickets and operational work.
- `viewer`: read-only access.

Canonical source:

```text
project_members(project_id, user_id, role)
```

Compatibility endpoints may still accept Telegram chat ids, but they must
translate them into platform users plus `project_members` rows.

## Contacts And CRM

`clients` is the project-scoped CRM/contact table.

Current contact fields:

- `project_id`
- `user_id`
- `chat_id`
- `username`
- `full_name`
- `email`
- `company`
- `phone`
- `metadata`
- `crm_contact_id`
- `source`

Important rules:

- `clients.email`, `clients.company`, `clients.phone` describe the person inside
  one business/project context.
- `users.email` describes platform authentication identity.
- Built-in CRM tools must read/write `clients`, never `users`.
- Searching clients should search identity-like contact fields and CRM fields:
  username, full name, email, company and phone.

## Channels And Surfaces

Canonical channel model:

```text
project_channels(project_id, kind, provider, status, config_json)
```

Channel kind examples:

- `client`
- `manager`
- `widget`
- `platform`

Provider examples:

- `telegram`
- `web`
- future providers such as WhatsApp.

Rules:

- Channel kind is infrastructure/surface metadata, not complete domain truth.
- Platform bot must use `/webhooks/platform`.
- Project client bot must use `/webhooks/projects/{project_id}/client`.
- Project manager bot must use `/webhooks/projects/{project_id}/manager`.
- Web widget/chat must use the project-plane message pipeline and create/update
  a project-scoped `clients` contact with `source='web'`.
- Legacy `/webhook/{project_id}` is compatibility-only for client bot delivery.
- Tokens and webhook secrets authenticate transport; they do not determine
  project roles.
- Legacy `ADMIN_API_TOKEN` must not protect active domain/control-plane routes;
  platform administration uses JWT plus `users.is_platform_admin`, while
  project operations use `project_members`.

## Personalization

Personalization is first-class project data:

- `project_settings`: brand, industry, tone, language, timezone, prompt override.
- `project_policies`: escalation, routing, CRM, response and privacy policies.
- `project_integrations`: CRM, n8n, webhooks and future external systems.
- `project_limit_profiles`: token/request/concurrency/fallback model limits.
- `project_channels`: delivery surfaces.
- `project_prompt_versions`: prompt bundle versions and rollback points.

Runtime should receive this configuration explicitly and make behavior decisions
from it.

## Threads And Tickets

Manual handling must be assigned to platform users, not Telegram-only managers.

Canonical thread assignment:

- `threads.manager_user_id`

Legacy bridge:

- `threads.manager_chat_id`

Canonical task/ticket assignment:

- `tasks.assigned_user_id`
- `tasks.created_by_user_id`

Legacy bridges:

- `tasks.assigned_to`
- `tasks.created_by`

Rules:

- Web manager actions should pass `manager_user_id` directly.
- Telegram manager actions may include `manager_chat_id`, but must resolve it to
  a project member user before domain state is updated.
- If a Telegram manager chat id cannot resolve to a `project_members` user for
  the project, manager application services must deny the action before writing
  Redis reply sessions, thread assignment, messages or tickets.
- Returning a thread to AI handling must clear manager assignment.
- Future task APIs must expose user-based assignment fields.

Web widget rules:

- A browser visitor must have a stable visitor id.
- Backend maps that visitor id to a stable project-scoped contact key.
- Widget messages must go through the same runtime/project-plane pipeline as
  Telegram client messages.

## Physical Package Structure

Canonical backend packages:

- `src/domain`: pure domain rules and value-level policy helpers.
- `src/application`: use cases and application services that coordinate domain
  rules with repositories/adapters.
- `src/interfaces/http`: FastAPI routers, HTTP dependency wiring and canonical
  ASGI/FastAPI application assembly in `src/interfaces/http/app.py`.
- `src/interfaces/telegram`: Telegram transport adapters for platform, client
  and manager bot surfaces.
- `src/interfaces/telegram/platform_admin`: control-plane Telegram bot command
  handlers, keyboards and knowledge-upload helpers.
- `src/infrastructure/db`: database models and SQL repositories.
- `src/infrastructure/config`: environment/settings loading.
- `src/infrastructure/app`: application startup/shutdown lifecycle wiring.
- `src/infrastructure/logging`: logging and request correlation middleware.
- `src/infrastructure/redis`: Redis client and distributed locks.
- `src/infrastructure/llm`: model registry, model selection, embeddings, RAG,
  chunking and provider rate-limit tracking.
- `src/infrastructure/queue`: background worker and queue processing adapters.
- `src/infrastructure/telegram`: Telegram infrastructure helpers when transport
  code needs to be split further.

Legacy cleanup status:

- Old facade packages under `src/api`, `src/database`, `src/services`,
  `src/core`, `src/admin`, `src/clients` and `src/managers` have been removed.
- Old executable facades `src/main.py` and `src/worker.py` have been removed.
- Active entrypoints now use canonical modules directly:
  `src.interfaces.http.app:app` and `src.infrastructure.queue.worker`.

Rules:

- New production code must import canonical packages only.
- Removed facade paths must stay absent.
- `tests/architecture/test_import_boundaries.py` must fail if production code
  starts importing old facade packages again or if removed legacy paths
  reappear.

## Application Layer Rules

Layer direction:

- `interfaces` call `application`.
- `application` calls domain rules and repository ports/concrete repositories.
- `domain` must not import FastAPI, SQLAlchemy, Telegram SDK, Redis or HTTPX.
- Transport handlers must not decide domain truth.

Current practical conventions:

- FastAPI endpoints should use application services such as `ProjectService`.
- Repositories own SQL.
- API modules should not contain ad hoc project-role checks.
- Project access checks should go through `ProjectService.require_project_role`.

## Event Streams

`events.stream_id` is a historical technical name for the event stream key.
In the current runtime it corresponds to `thread_id`.

Rules:

- Do not introduce a second competing event thread identifier.
- If the DB column is renamed later, migrate it as a coordinated event-store
  migration.
- Until then, document it as `thread_id` semantics in code and tests.

## Removed Legacy Concepts

These must not be reintroduced:

- `projects.owner_id` as runtime owner.
- `users.project_id`.
- `project_managers`.
- `workflow_templates` and project `template_slug`.
- chat-id-only manager authorization.
- platform routing inferred by project bot token equality.
- admin API authorization inferred by static bearer token equality.
- CRM contacts stored in `users`.

## Current Migration Direction

Already established by migrations:

- Auth/membership/personalization foundation.
- `owner_id` demoted and dropped.
- `users.project_id` dropped.
- `project_managers` backfilled into `project_members` and dropped.
- workflow templates dropped.
- `clients.user_id` bridge added.
- CRM fields added to `clients`.
- CRM-only fields dropped from `users`.
- `threads.manager_user_id` added as manual thread assignment.
- `tasks.assigned_user_id` and `tasks.created_by_user_id` added for tickets.
- `users.is_platform_admin` added for global platform administration.

When adding future migrations:

- Keep Telegram login operational.
- Backfill before dropping old data.
- Prefer additive migrations before switching code paths.
- Remove compatibility only after code and tests no longer depend on it.

## Test Invariants

Tests must protect these contracts:

- Telegram login still works.
- Platform owner bootstrap marks exactly the configured Telegram identity as
  `users.is_platform_admin=true` without creating project-scoped roles.
- Email and Google login/linking attach providers to the same `user`.
- Project access is membership-based.
- Project owner is `projects.user_id`.
- Manager notification targets derive from `project_members` plus Telegram-linked
  platform users.
- Manual thread claim writes `threads.manager_user_id`.
- Client/contact APIs are project-scoped.
- CRM tools operate on `clients`.
- Platform webhook uses only `/webhooks/platform`.
- Client/manager webhooks use explicit project-plane surfaces.
- Admin/control-plane API routes do not use `ADMIN_API_TOKEN` as domain
  authorization.
- Web chat endpoint calls `process_message` with `source='web'`.
- Runtime prompt includes explicit project configuration.
