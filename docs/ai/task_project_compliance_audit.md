# Task: Project Compliance Audit Against AI Engineering Documents

You are Codex working in this repository.

Use these documents as the required standard:
- `AGENTS.md`
- `CODEX.md`
- `docs/ai/project_contract.md`
- `docs/ai/quality_bar.md`
- `docs/ai/backend_rules.md`
- `docs/ai/frontend_rules.md`
- `docs/ai/security_rules.md`
- `docs/ai/performance_rules.md`

## Goal

Check whether the current project conforms to the standards described in those documents.

This is an audit task only.

Do not modify source code unless explicitly asked later.

## Required inspection

Inspect the repository directly.

Check at least:

### Architecture

- repository layout;
- layer boundaries;
- architecture tests;
- imports from `src/domain`;
- imports from `src/application`;
- imports from `src/infrastructure`;
- imports from `src/interfaces`;
- imports from `src/agent`;
- composition/wiring boundaries.

### Typing

- use of `Any`;
- broad casts;
- `type: ignore`;
- untyped dynamic payloads in source;
- agent node contracts;
- runtime state contracts;
- DTO/view-model patterns.

### Complexity

- large functions;
- deeply nested code;
- policy mixed with IO;
- transport mixed with business logic;
- repeated logic;
- files likely to increase maintenance risk.

Use available project tools if installed, such as radon, ruff, mypy, pytest, grep/rg, and Python AST scripts.

### Lazy imports and startup hygiene

Check whether plain app import pulls heavy optional dependencies.

Pay attention to:
- `langchain_groq`;
- `ChatGroq`;
- `langgraph`;
- `PyPDF2`;
- `pypdf`;
- `fastembed`;
- `sentence_transformers`;
- `torch`;
- `transformers`.

### Security

Check:
- secret patterns in tracked files;
- unsafe logging;
- token/webhook secret handling;
- database URL exposure;
- SQL construction patterns;
- webhook routing/security;
- LLM output validation;
- memory persistence safety.

Do not print real secrets if found. Mask them.

### Performance

Check:
- heavy module imports;
- unbounded loops;
- prompt context limits;
- repeated DB calls;
- repeated LLM calls;
- repository query patterns;
- hot webhook/runtime paths.

### Tests and validation

Check:
- available test suites;
- architecture tests;
- backend quality commands;
- frontend quality commands if frontend exists;
- whether current checks pass.

Run reasonable checks. Do not waste time repeating the same command.

## Output format

Produce a concise audit result with:

1. Overall verdict:
   - PASS
   - REVIEW
   - FAIL

2. Executive summary:
   - what conforms well;
   - what is risky;
   - what should be fixed first.

3. Findings grouped by severity:
   - Blocker
   - High
   - Medium
   - Low

4. For each finding:
   - file/path;
   - short evidence;
   - why it matters;
   - recommended fix direction;
   - whether code changes are required.

5. Validation performed:
   - commands run;
   - pass/fail result;
   - limitations.

6. Recommended next patch sequence:
   - smallest safe order;
   - tests to run for each step.

## Constraints

- Do not edit files.
- Do not generate large reports unless needed.
- Do not expose secrets.
- Do not overstate certainty.
- Do not suggest generic rewrites.
- Prefer precise, local, actionable findings.
