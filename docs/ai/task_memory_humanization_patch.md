# Task: Memory and Humanized Response Quality Patch

You are Codex working in this repository.

Use these documents as the required standard:
- `AGENTS.md`
- `CODEX.md`
- `docs/ai/project_contract.md`
- `docs/ai/quality_bar.md`
- `docs/ai/backend_rules.md`
- `docs/ai/security_rules.md`
- `docs/ai/performance_rules.md`

## Goal

Improve response humanization through better use of user replies and memory, without degrading architecture, type safety, security, performance, or complexity.

This is not a prompt-library dump task.

The goal is to make the runtime better at:
- understanding user replies;
- remembering useful stable context;
- avoiding naive keyword-only intent handling;
- using memory in prompts more cleanly;
- producing more human, less generic answers.

## Required recon before patching

Inspect directly:

- memory repository;
- memory ports;
- load-state node;
- persist node;
- dialog_state domain logic;
- persistence domain logic;
- intent extractor domain contract;
- intent extractor node;
- prompt builder;
- response generator node;
- response prompt;
- intent prompt;
- policy decision engine;
- repeat detection;
- state contracts;
- tests around those areas.

Identify existing flow:
1. where memory is loaded;
2. how memory is indexed by type;
3. how dialog_state is created and persisted;
4. how intent/emotion/topic/cta/features are extracted;
5. how history and memory enter prompts;
6. where deterministic memory write gates belong;
7. where prompt changes are safest.

## Desired design direction

Prefer a minimal schema-compatible design.

Do not add DB schema unless truly necessary.

Prefer:
- typed domain helpers;
- deterministic memory write candidates;
- validated structured LLM extraction extension if needed;
- conservative persistence rules;
- explicit memory types and keys;
- tests around extraction and persistence;
- compact prompt formatting.

Do not:
- let LLM write memory directly;
- store raw sensitive messages unnecessarily;
- overwrite durable facts from weak evidence;
- add broad untyped JSON blobs deep in domain;
- add another full LLM call only for memory unless strongly justified;
- increase graph complexity unnecessarily;
- create a large generic memory framework.

## Humanization target

Improve final responses by giving the response generator better context, not by adding fake personality.

Good humanization:
- remembers stable client preferences;
- remembers objections and constraints;
- remembers business context when confidently known;
- reacts to user emotion safely;
- avoids generic corporate phrases;
- uses concise natural language;
- asks the next useful question;
- respects RAG facts and project configuration.

Bad humanization:
- fake slang;
- overfamiliar tone;
- invented facts;
- excessive style prompts;
- storing unsafe personal data;
- using hostile user language;
- making responses longer.

## Implementation constraints

- Keep domain pure.
- Keep agent node contracts typed.
- No `Any`.
- No broad type ignores.
- No heavy imports.
- No architecture boundary violations.
- No raw secret logging.
- No large unrelated rewrites.
- No increased cyclomatic complexity.
- Add or update focused tests.

## Suggested patch shape

Prefer one of these small approaches if it fits the actual code:

### Option A: deterministic memory write gate

Add a domain-level helper that takes current runtime state and returns typed memory write candidates.

Example concepts:
- stable user preference;
- rejection/objection;
- support issue summary;
- business context;
- contact preference;
- pricing sensitivity.

The helper must be conservative and testable.

Persistence node applies those candidates through existing memory repository.

### Option B: extend intent extraction payload safely

If current intent extraction is too shallow, extend its structured output with typed fields that already fit the runtime:

- risk;
- temperature/emotion refinement;
- user_reply_kind;
- objection_type;
- memory_hints.

Only persist memory hints after deterministic validation.

### Option C: improve prompt formatting

Improve how memory is formatted into intent/response prompts:
- group useful memory;
- avoid noisy internal state;
- keep compact limits;
- make dialog_state useful but not dominant;
- preserve project config and RAG priority.

## Required validation

Run focused tests around:
- intent extraction;
- persistence;
- dialog_state;
- memory repository or memory contracts;
- prompt builder;
- response generation;
- policy decision if touched;
- architecture tests if imports changed.

Run type/lint checks for touched areas.

If the change is cross-cutting, run full backend checks.

## Output

After patching, provide:
- summary of changed files;
- why the design is safe;
- tests run;
- remaining limitations;
- suggested next step.
