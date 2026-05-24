# crm_bot Codex Implementation Workflow

Use for non-trivial implementation tasks.

1. Read `AGENTS.md`.
2. Use `search-first` and `iterative-retrieval`.
3. Spawn read-only mappers/reviewers as needed:
   - `planner`
   - `architect`
   - `backend_mapper`
   - `frontend_mapper`
   - `database_reviewer`
   - `typescript_reviewer`
   - `python_reviewer`
   - `tdd_guide`
   - `security_reviewer`
4. Produce plan before patching.
5. Use `implementer`, `build_error_resolver`, `refactor_cleaner`, or `doc_updater` only after the plan.
6. Run focused validation.
7. Run `reviewer` before final answer.
8. Do not commit or push unless explicitly requested.
