# crm_bot Codex Build Fix Workflow

Use when lint/type-check/build/tests fail.

1. Read `AGENTS.md`.
2. Inspect the exact failing command output.
3. Spawn `build_error_resolver`.
4. Spawn stack reviewer if relevant:
   - `typescript_reviewer`
   - `python_reviewer`
   - `database_reviewer`
5. Patch minimally.
6. Rerun the exact failing command.
7. Run adjacent gates if the fix touched broader code.
