# Agent Operating Contract

This repository is a production codebase. Any AI coding agent working here must preserve or improve code quality, architecture, security, performance, maintainability, and testability.

The primary goal is not to make a quick patch. The primary goal is to produce clean, production-ready code that fits the existing system.

## Mandatory behavior

Before changing code, inspect the current implementation deeply.

You must:
- read the relevant files directly;
- inspect nearby patterns before inventing new ones;
- identify call sites;
- identify existing tests;
- identify architecture boundaries;
- understand runtime side effects;
- understand data contracts;
- understand security implications;
- choose the smallest safe change that solves the task;
- avoid expanding scope without a clear reason.

Do not patch from grep results alone.

Do not make broad edits when a targeted change is enough.

Do not hide uncertainty. If part of the system is unclear, inspect more code before editing.

## Quality bar

Generated code must look like it was written by a careful senior engineer maintaining this repository.

Code must be:
- production-ready;
- typed;
- readable;
- cohesive;
- low-complexity;
- deterministic where possible;
- safe under failure;
- easy to review;
- consistent with nearby code;
- covered by relevant tests;
- compatible with existing architecture.

A passing test suite is required, but it is not enough. A patch is unacceptable if it passes tests while degrading architecture, typing, readability, performance, security, or maintainability.

## Forbidden shortcuts

Do not:
- add `Any` unless there is a strong local justification and no better type is practical;
- use `cast(Any, ...)`;
- add broad `# type: ignore` comments to silence problems;
- replace precise types with vague `object` mechanically;
- create god-functions;
- create generic abstraction layers without a real need;
- duplicate DTOs or contracts unnecessarily;
- add temporary comments, TODO-driven code, or scaffolding leftovers;
- swallow errors silently;
- leak secrets into logs, reports, exceptions, test output, or generated files;
- move infrastructure concerns into domain code;
- import heavy runtime dependencies at module import when lazy import is already the project pattern;
- simplify nuanced existing frontend design into generic UI;
- break generated API contracts;
- modify unrelated files;
- commit or push unless explicitly instructed.

## Recon expectation

Recon is mandatory, but reports are not mandatory.

Use the repository tools directly. Read files. Inspect tests. Run targeted commands.

Create temporary notes only when the task is large or risky. Do not generate verbose reports by default.

The required outcome of recon is that your patch reflects actual understanding of the existing code.

## Patch discipline

Before editing:
- identify the minimal files to touch;
- check existing style in those files;
- check relevant tests;
- check architecture boundaries;
- check failure modes.

While editing:
- keep changes small and local;
- preserve public contracts unless the task explicitly requires changing them;
- preserve backwards compatibility where practical;
- prefer pure domain logic for policy decisions;
- keep side effects at infrastructure, interface, or composition boundaries;
- avoid increasing cyclomatic complexity;
- split logic into clear small functions when needed;
- keep names precise and boring.

After editing:
- run focused tests first;
- run type and lint checks relevant to changed areas;
- run broader checks when the change is cross-cutting;
- inspect the final diff before declaring done;
- verify no secrets were introduced;
- verify no architecture boundary was violated;
- verify complexity did not regress.

## Architecture boundaries

Respect the repository layering.

Domain code:
- pure business/runtime contracts;
- no FastAPI;
- no DB clients;
- no Redis;
- no Telegram clients;
- no LLM SDKs;
- no filesystem side effects unless explicitly part of a pure parser contract.

Application code:
- coordinates use cases;
- depends on ports, DTOs, and domain contracts;
- does not import interface adapters;
- does not own external SDK details.

Infrastructure code:
- implements repositories, Redis, queues, LLM, embeddings, storage, external adapters;
- may depend on domain/application contracts;
- must not leak infrastructure concerns into domain.

Interfaces code:
- owns HTTP, Telegram, request/response handling;
- delegates business decisions to application/domain/runtime services.

Agent code:
- wires graph nodes and runtime adapter behavior;
- must keep contracts typed;
- must avoid importing heavy LLM/langgraph packages at plain app import unless explicitly required by composition.

Tools code:
- exposes controlled tool behavior;
- validates inputs;
- handles failure safely.

Frontend code:
- preserves the existing visual system;
- uses existing tokens, components, spacing, typography, and layout patterns;
- does not introduce random colors or one-off UI conventions;
- preserves API contracts and behavior.

## Typing rules

Prefer:
- `Protocol`;
- `TypedDict`;
- `Mapping[str, object]`;
- dataclasses;
- concrete DTO/view-model types;
- narrow helper functions;
- explicit return types.

Avoid:
- `Any`;
- untyped dict soup;
- unvalidated dynamic payloads;
- broad casts;
- type ignores.

If dynamic JSON is unavoidable, keep it at boundaries and validate it into typed structures before using it deeper in the system.

## Complexity rules

Do not increase cyclomatic complexity unnecessarily.

Prefer:
- simple linear control flow;
- small focused helpers;
- declarative mappings;
- typed result objects;
- pure functions for decision logic.

Avoid:
- nested condition pyramids;
- giant functions;
- mixed IO and policy logic;
- hidden mutable global state;
- implicit behavior spread across unrelated files.

## Security rules

Secrets must never be printed or stored in generated artifacts.

Treat these as secrets:
- database URLs;
- bot tokens;
- API keys;
- webhook secrets;
- encryption keys;
- JWT secrets;
- OAuth secrets;
- service credentials.

When logging:
- log structured context;
- mask sensitive values;
- avoid raw request bodies if they may contain secrets or personal data;
- never log full tokens.

When handling external services:
- assume Telegram, LLM providers, Redis, DB, HTTP APIs, embeddings, and file parsers can fail;
- provide deterministic fallback or safe degradation;
- do not turn failures into silent success;
- preserve observability without leaking secrets.

## Performance rules

Do not add avoidable expensive work to hot paths.

Avoid:
- heavy module-level imports;
- unnecessary full-table scans;
- unbounded loops;
- repeated LLM calls;
- repeated DB calls where one query is enough;
- loading large files fully without need;
- blocking IO in async paths.

Prefer:
- lazy imports for heavy optional dependencies;
- bounded limits;
- indexed queries;
- async-safe operations;
- caching only when correctness is clear.

## Testing rules

Choose tests based on the change.

For domain logic:
- run focused domain tests;
- add or update unit tests.

For agent/runtime changes:
- run relevant agent node, runtime contract, policy, prompt builder, and architecture tests.

For repository changes:
- run repository tests and migration checks where relevant.

For HTTP/Telegram changes:
- run API tests and interface tests.

For frontend changes:
- run lint, type-check, and build from the frontend package.

For cross-cutting changes:
- run the full backend quality gate.

Do not repeatedly run the same checks without changing anything.

## Done definition

A task is done only when:
- the change solves the requested problem;
- code quality is preserved or improved;
- relevant tests pass;
- typing passes for touched areas;
- lint/format checks pass for touched areas;
- architecture boundaries remain intact;
- no secrets are exposed;
- complexity is not increased without justification;
- final diff is coherent and reviewable.
