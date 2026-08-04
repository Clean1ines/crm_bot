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


<!-- BEGIN MVP WORK ITEM OVERRIDE -->

## Pilot backlog override

If the user names a Pilot v0.1 backlog item (`S1.1`, `S1.2`, and so on), do not use this generic workflow as the primary workflow.

Use `.codex/workflows/mvp-work-item.md` instead. That workflow adds mandatory task resolution, specification/ADR freshness checks, pre-implementation QA design, impact analysis, independent acceptance review, release-document synchronization, evidence generation, and gated local commit behavior.

The generic implementation workflow remains the fallback for non-backlog implementation tasks.

<!-- END MVP WORK ITEM OVERRIDE -->
