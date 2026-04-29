# Codex Task Contract

Follow `AGENTS.md` and all files under `docs/ai/`.

Your job is to produce production-ready code, not quick patches.

Before editing, perform deep recon by reading the repository:
- relevant implementation files;
- nearby patterns;
- call sites;
- tests;
- type contracts;
- architecture boundary tests;
- runtime side effects;
- failure modes.

Do not generate verbose reports by default. Use direct inspection and focused commands. Create temporary notes only when useful.

Do not start editing until you understand the existing design.

## Non-negotiable constraints

- Do not add `Any` unless explicitly justified.
- Do not use broad `type: ignore`.
- Do not increase cyclomatic complexity.
- Do not break architecture boundaries.
- Do not introduce heavy module-level imports.
- Do not leak secrets.
- Do not rewrite unrelated code.
- Do not create generic abstractions without need.
- Do not simplify existing frontend design into generic UI.
- Do not commit or push unless explicitly told.

## Required validation

After changes, run the smallest useful checks first, then broader checks if the change is cross-cutting.

Always inspect the final diff before finishing.

If checks fail, fix the cause instead of weakening tests or types.
