## 0. Проверка ref / mandatory commands

Локальные команды:

```bash
cd /home/haku/crm_bot
git status --short
git log --oneline -35
```

через GitHub-коннектор выполнить нельзя, поэтому **dirty working tree локально не подтверждён**. Через GitHub проверен `main`:

| field                 | result                                                                                     |
| --------------------- | ------------------------------------------------------------------------------------------ |
| checked_ref           | `main`                                                                                     |
| current_branch        | локально не проверено                                                                      |
| local_changes_present | локально не проверено                                                                      |
| latest commit hash    | `acdcdb4c5c9ad197706a0efb41743bceec368fd8`                                                 |
| latest commit         | `Add compaction capacity window correlation`                                               |
| Patch 17E present?    | да, docs описывают ClaimBuilder attempt outcome visibility.                                |
| Patch 18D present?    | да, docs описывают active frontier correctness.                                            |
| Patch 18E present?    | да, docs описывают compaction frontier read contract.                                      |
| Patch 18F present?    | да, latest commit и docs описывают CapacityWindow correlation для dynamic compaction work. |

---

# 1. Short verdict

```text
implementation_ready_for_next_patch: yes, для contract/read/projection patch; no, для полного frontend reducer
recommended_next_patch_title: Patch 19A — Compaction document-card reducer contract and attempt append readiness
recommended_boundary: compaction projection/read contract → dynamic reduction work rows → ClaimBuilder-style attempt append → CapacityWindow dashboard source model
```

**Что ClaimBuilder уже решает:** у него есть нормальная форма `SourceUnit surface → WorkItem overlay → Attempts list`; attempt outcome содержит `attempt_scope`, `provider_outcome`, `validation_outcome`, `persistence_outcome`, `work_item_outcome`, `capacity_annotation`, `targeted_read_hint`. Успешный ClaimBuilder event также даёт `draft_claim_observation_rows` и targeted read scope для загрузки тел строк.

**Что Compaction ещё не закрывает как document-card workflow:** backend уже имеет compaction projection events, frontier read contract, generated-node targeted read и pending reduction work rows. Но frontend всё ещё строит compaction UI из `workflow-live-state` snapshot, а не из reducer entities. Плюс compaction attempt projector всё ещё выводит `batch_ref` из `work_item_id` строковым prefix parsing, что противоречит принципу “frontend reducer must not infer graph by string parsing”.

**Почему этот patch сейчас:** надо зафиксировать deterministic event-to-entity contract для compaction до React reducer. Иначе reducer начнёт угадывать parent row: ClusterBatch? pending work? generated node? frontier input set? Это особенно опасно после 18F, где dynamic work row keyed by `work_item_id`, а не fake ClusterBatch.

**Почему не reducer прямо сейчас:** event projection stream уже есть на backend, но frontend всё ещё подписан на старый `workflow-live-state/events`, который доставляет полный snapshot. Projection stream endpoint есть отдельно, но KnowledgePage его не использует.

**Почему не curation/publication:** compaction final active nodes ещё не стали нормально видимыми в document-card как reducer surfaces/overlays; capacity-blocked state и retry attempts тоже не видны как отдельные rows. Curation/publication позже, после закрытия compaction document-card artifact surface.

---

# 2. ClaimBuilder vs Compaction matrix

| concern                         | ClaimBuilder current behavior                                                                                                               | Compaction current behavior                                                                                         | target compaction behavior                                                                                                                       | gap                                                                    |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------- |
| artifact row identity           | `SourceUnit` row + `WorkItem` overlay + `DispatchAttempt` history; scope содержит `source_unit_ref`, `work_item_id`, `dispatch_attempt_id`. | ClusterGroup/Batch, frontier nodes, pending work, attempts существуют разными read/projection paths.                | Не один parent. Compaction visual graph должен иметь `cluster_groups`, `cluster_batches`, `compaction_frontier_nodes`, `pending_reduction_work`. | Нет единой frontend entity map.                                        |
| attempt identity                | `dispatch_attempt_id` — stable key attempt row.                                                                                             | `dispatch_attempt_id` есть в compaction attempt payload.                                                            | `compaction_attempts[dispatch_attempt_id]`, linked to `pending_reduction_work[work_item_id]`.                                                    | Parent fields неполные.                                                |
| retry append                    | ClaimBuilder retryable event обновляет WorkItem overlay и добавляет attempt outcome payload.                                                | Compaction retryable event даёт attempt payload с `work_item_state=retryable_failed`.                               | Retry attempt appends under same dynamic work row / work item history, not overwrites entire parent graph.                                       | Frontend reducer отсутствует.                                          |
| generated artifact availability | DraftClaimObservation rows appear from successful ClaimBuilder extracted event via `draft_claim_observation_rows`.                          | Generated compaction nodes appear only on `ResultApplied`, not on attempt completed.                                | Treat `ResultApplied` as generated node surface boundary.                                                                                        | Need reducer action that does targeted read after `ResultApplied`.     |
| targeted read after result      | ClaimBuilder uses `/workflows/{workflow_run_id}/draft-claims?...`.                                                                          | Compaction has `/draft-claim-compaction-nodes` and `/draft-claim-compaction-frontier`.                              | Use nodes read for generated node bodies and frontier read for active state/pending work.                                                        | Current UI does not call them for document-card reducer.               |
| capacity overlay                | ClaimBuilder capacity projection can annotate WorkItem/attempt and CapacityWindow.                                                          | 18F added compaction_context to capacity events and projected targeted read for pending work.                       | Update `capacity_windows[window_key]` and linked `pending_reduction_work[work_item_id]`.                                                         | No CapacityWindow dashboard reducer/store.                             |
| pending work visibility         | ClaimBuilder lanes show queue items from snapshot.                                                                                          | Compaction frontier read exposes `pending_work_summary` + `pending_work_items`.                                     | `pending_reduction_work[work_item_id]` is first-class row.                                                                                       | No event creates/updates it without targeted read.                     |
| dynamic next work               | ClaimBuilder schedule is tied to source units.                                                                                              | `NextWorkScheduled` says work scheduled, but must not invent ClusterBatch rows.                                     | Trigger frontier/pending-work targeted read; create dynamic rows from read model.                                                                | Projection only points to node read, not explicitly pending work read. |
| cluster/group parent row        | ClaimBuilder parent is source unit.                                                                                                         | ClusterGroup is parent, ClusterBatch is only initial batch surface; dynamic work may not belong to persisted batch. | ClusterGroup is high-level parent; pending work is execution row; frontier node is artifact row.                                                 | Current attempt payload derives batch from string prefix.              |
| row completion                  | ClaimBuilder completed event completes WorkItem and makes claims available.                                                                 | Compaction attempt completed only means provider/validation done; `ResultApplied` changes node graph.               | Attempt completed updates attempt; ResultApplied updates frontier/generated nodes.                                                               | Need reducer not to mark generated nodes on attempt completed.         |
| timeline/history                | Snapshot has attempts/timeline.                                                                                                             | Projection events exist, but frontend still snapshot.                                                               | Append attempts by `dispatch_attempt_id`, preserve history under work row.                                                                       | No frontend projection reducer.                                        |
| heavy body guard                | ClaimBuilder projection excludes claim bodies; targeted read loads bodies.                                                                  | Compaction projector explicitly forbids heavy bodies and timers.                                                    | Keep bodies in targeted reads only.                                                                                                              | Good backend guard, UI not wired.                                      |

---

# 3. Reducer entity model

| entity                      | key                          | surface / overlay / history | created by                                            | updated by                            | targeted read                                 | gap                                     |
| --------------------------- | ---------------------------- | --------------------------- | ----------------------------------------------------- | ------------------------------------- | --------------------------------------------- | --------------------------------------- |
| `documents`                 | `document_ref` / document id | surface                     | document list/bootstrap                               | workflow/document events              | document list/live-state bootstrap            | ok                                      |
| `workflows`                 | `workflow_run_id`            | surface + overlay           | workflow started/bootstrap                            | phase/progress/action events          | live-state bootstrap/recovery                 | ok, but realtime still snapshot         |
| `source_units`              | `source_unit_ref`            | surface                     | `SourceUnitsCreated` / source-units read              | claim-builder overlays                | source-units endpoint                         | ok                                      |
| `draft_claim_rows`          | `observation_ref`            | surface                     | ClaimBuilder extracted row availability               | embedding/cluster membership overlays | `getDraftClaimsByWorkflowScope`               | ok backend/frontend wrapper exists.     |
| `cluster_groups`            | `group_ref`                  | surface                     | `workflow_draft_claim_clusters_built` + targeted read | compaction status / group done        | `getDraftClaimClustersByWorkflow`             | needs reducer                           |
| `cluster_batches`           | `batch_ref`                  | initial surface             | cluster targeted read includes batches                | initial compaction overlay            | cluster read                                  | dynamic work must not be forced here    |
| `compaction_frontier_nodes` | `node_ref`                   | surface                     | initial seed / `ResultApplied` targeted read          | active/inactive/frontier state        | frontier/nodes reads                          | needs reducer + targeted read call      |
| `pending_reduction_work`    | `work_item_id`               | surface + overlay           | frontier read `pending_work_items`                    | dispatch/attempt/capacity events      | frontier read currently includes pending work | needs projection action to trigger read |
| `compaction_attempts`       | `dispatch_attempt_id`        | append-only history         | dispatch prepared / attempt event                     | provider/validation/work outcome      | no dedicated attempt read verified            | attempt endpoint/read missing           |
| `capacity_windows`          | `window_key`                 | surface + overlay           | capacity observed/exhausted/leased/wakeup             | capacity events                       | no standalone dashboard read verified         | dashboard read/model missing            |
| `curation_items`            | `item_ref`                   | surface                     | curation workspace open/read                          | include/exclude/edit/publish overlays | curation workspace endpoint                   | later                                   |

Key point: **visual row for dynamic compaction work should be `pending_reduction_work[work_item_id]`**, not `cluster_batches[batch_ref]`. `ClusterBatch` remains initial cluster/batch surface; after generated nodes create more work, row identity is dynamic work item / frontier node graph. Docs explicitly say dynamic compaction work is pending reduction work keyed by `work_item_id`, not fake ClusterBatch rows.

---

# 4. Compaction event action map

| projection_type                                            | action                                      | entity key                                                                         | parent key                               | append / update / create                               | targeted read                                                     | gap                                                                              |
| ---------------------------------------------------------- | ------------------------------------------- | ---------------------------------------------------------------------------------- | ---------------------------------------- | ------------------------------------------------------ | ----------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `workflow_draft_claim_clusters_built`                      | mark cluster surfaces available             | `cluster_groups[group_ref]` after read                                             | `workflow_run_id`                        | create surfaces after read                             | `getDraftClaimClustersByWorkflow`                                 | projection payload not enough for all rows                                       |
| `workflow_draft_claim_compaction_dispatch_batch_prepared`  | create/prepare work overlays                | `pending_reduction_work[work_item_id]`, `compaction_attempts[dispatch_attempt_id]` | group unknown until read                 | create attempt shell + schedule pending work read      | frontier/pending work read                                        | payload has work/attempt ids but not group/input refs.                           |
| `workflow_draft_claim_compaction_attempt_completed`        | append attempt outcome                      | `compaction_attempts[dispatch_attempt_id]`                                         | `pending_reduction_work[work_item_id]`   | append history + update work overlay completed         | no, unless missing parent                                         | attempt completed must not create generated node                                 |
| `workflow_draft_claim_compaction_attempt_retryable_failed` | append retryable attempt                    | `compaction_attempts[dispatch_attempt_id]`                                         | `pending_reduction_work[work_item_id]`   | append history + set retryable overlay                 | maybe no                                                          | retry later appends new attempt under same work item                             |
| `workflow_draft_claim_compaction_attempt_terminal_failed`  | append terminal attempt                     | `dispatch_attempt_id`                                                              | `work_item_id`                           | append + terminal overlay                              | maybe no                                                          | terminal does not consume input nodes                                            |
| `workflow_draft_claim_compaction_result_applied`           | generated nodes available; frontier changed | `compaction_frontier_nodes[node_ref]` after read                                   | `group_ref`, `batch_ref`, `work_item_id` | create generated nodes + update superseded nodes       | `getDraftClaimCompactionNodesByWorkflow` and likely frontier read | must not be treated as attempt success only.                                     |
| `workflow_draft_claim_compaction_next_work_scheduled`      | progress signal; new dynamic work may exist | `pending_reduction_work[work_item_id]` after read                                  | `group_ref`                              | update group pending status; create rows from read     | frontier/pending work read                                        | projection targeted read currently points to nodes, not explicitly pending work. |
| `workflow_draft_claim_compaction_cluster_done`             | mark group completed                        | `cluster_groups[group_ref]`                                                        | `workflow_run_id`                        | update overlay                                         | no                                                                | ok                                                                               |
| `workflow_draft_claim_compaction_all_groups_compacted`     | document compaction completed               | `workflows[workflow_run_id]` / document                                            | workflow/document                        | update document compaction overlay, curation readiness | maybe frontier final read                                         | ok                                                                               |
| `workflow_capacity_window_observed`                        | update capacity counters                    | `capacity_windows[window_key]`                                                     | optional attempt/work item               | update overlay                                         | no                                                                | observed projector not opened here; docs confirm contract                        |
| `workflow_capacity_window_exhausted`                       | mark window sleeping/exhausted              | `capacity_windows[window_key]`                                                     | optional work/attempt/group              | update overlay + linked work capacity_waiting          | maybe pending work read if compaction_context                     | ok with 18F context                                                              |
| `workflow_capacity_window_scheduled_wakeup`                | set wakeup/reset countdown                  | `capacity_windows[window_key]`                                                     | window                                   | update overlay                                         | no                                                                | dashboard needs countdown computed frontend                                      |
| `workflow_capacity_window_leased_work_item`                | attach capacity admission to work row       | `capacity_windows[window_key]`, `pending_reduction_work[work_item_id]`             | group/input refs via compaction_context  | update capacity overlay + work row active lease        | targeted read kind from compaction_context                        | ok for linked compaction work, no release event.                                 |

Idempotency key для reducer: `projection_event_id` + `projection_type`; для append history дополнительно `dispatch_attempt_id`. Frontend events endpoint возвращает `projection_event_id`, `source_event_id`, `source_sequence_number`, `projection_type`, payload и cursor.

---

# 5. Attempt append semantics table

| case                        | ClaimBuilder behavior                                               | Compaction target behavior                                                                               | current support                                                      | gap                                                  |
| --------------------------- | ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- | ---------------------------------------------------- |
| dispatch prepared           | attempt/work overlay created from dispatch prepared                 | create `compaction_attempts[dispatch_attempt_id]` and attach to pending work after targeted read         | dispatch projection has attempt/work ids.                            | lacks group/input refs in payload                    |
| leased/admitted             | capacity leased event annotates work/attempt/window                 | update `capacity_windows[window_key]`, link to `pending_reduction_work[work_item_id]`                    | compaction_context carries group/batch/input refs and targeted read. | no release event                                     |
| provider started            | no dedicated event; final outcome only                              | same later, but should become provider started overlay later                                             | absent                                                               | requires new event later                             |
| provider completed          | included in attempt_outcome provider block                          | included in compaction attempt provider_outcome                                                          | yes final-only                                                       | ok for next contract; finer events later             |
| validation failed retryable | retryable event appends outcome + work item retryable overlay       | append retryable attempt under same dynamic work row                                                     | yes attempt payload                                                  | parent row may need targeted read                    |
| provider failed retryable   | retryable event + capacity-owned skip if capacity reset             | append retryable, keep WorkItem passive eligibility                                                      | partial                                                              | exact provider reason granularity less rich          |
| terminal failed             | terminal event appends terminal outcome                             | append terminal attempt; do not consume frontier inputs                                                  | yes                                                                  | ok                                                   |
| result applied              | ClaimBuilder success also means draft rows available                | Compaction `ResultApplied` means generated nodes/frontier changed; attempt success alone is insufficient | yes, explicit projection.                                            | reducer not built                                    |
| retry creates next attempt  | new `dispatch_attempt_id` should append under same WorkItem history | same: append under `pending_reduction_work[work_item_id]`; not under generated node                      | current event keys support `work_item_id`/attempt id                 | frontend not implemented                             |
| dynamic next work           | not analogous; ClaimBuilder source unit rows are stable             | `NextWorkScheduled` triggers pending work/frontier targeted read; no fake batch rows                     | projection states no fake ClusterBatch.                              | targeted read should include pending work explicitly |

Conclusion: **Compaction retry should append to attempt history under dynamic work item / pending reduction work row. ClusterBatch is only parent for initial batch surfaces. Dynamic next work must not be forced into ClusterBatch.**

---

# 6. CapacityWindow dashboard matrix

| field                              | source / event / read model                                                        |                   available now |                    safe for frontend | gap                                                     |
| ---------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------: | -----------------------------------: | ------------------------------------------------------- |
| `window_key`                       | capacity projections build `provider:account_ref:model_ref`.                       |                             yes |                                  yes | ok                                                      |
| `provider`                         | capacity event payload                                                             |                             yes |                                  yes | ok                                                      |
| `account_ref`                      | capacity event payload                                                             |                             yes | yes, as safe account ref, not secret | no API key leak; keep redacted from secrets             |
| `model_ref` / `model_id`           | capacity event and pending work read model                                         |                             yes |                                  yes | naming `model_ref` vs `model_id` needs UI normalization |
| `work_kind`                        | compaction projection payload uses `knowledge_workbench.draft_claim_compaction`.   |                         partial |                                  yes | capacity event may not carry work_kind                  |
| `operation_key / phase`            | capacity projection includes operation/canonical phase                             |                             yes |                                  yes | ok                                                      |
| `remaining_minute_requests`        | `workflow_capacity_window_observed` docs                                           |                yes for observed |                                  yes | observed projector not inspected in this pass           |
| `remaining_minute_tokens`          | observed docs                                                                      |                yes for observed |                     yes, operational | product decision exact vs bucketed                      |
| `remaining_daily_requests`         | observed docs                                                                      |                yes for observed |                                  yes | product decision exact vs bucketed                      |
| `remaining_daily_tokens`           | observed docs                                                                      |                yes for observed |                                  yes | product decision exact vs bucketed                      |
| `reset_at`                         | exhausted/scheduled wakeup payload                                                 |                             yes |                                  yes | countdown computed frontend                             |
| `minute_reset_at / daily_reset_at` | observed payload expectation                                                       |                yes for observed |                                  yes | should stay CapacityWindow overlay only                 |
| `countdown_to_reset`               | computed frontend from reset_at                                                    |                 no direct field |                                  yes | frontend computed timer                                 |
| `active_lease_count`               | could aggregate leased events; no release event                                    |                         partial |                                  yes | requires read or release/expiry semantics               |
| `waiting_work_count`               | compaction frontier `pending_work_summary.waiting_for_capacity_count`              | yes for workflow/group frontier |                                  yes | no global CapacityWindow dashboard read                 |
| `leased_work_items`                | leased event gives one work item; pending work read has leased/running count/items |                         partial |                                  yes | no release event / current list endpoint by window      |
| `blocked_work_items`               | pending work items with `capacity_waiting` and `waiting_reason`                    |            yes in frontier read |                                  yes | no window-scoped dashboard endpoint                     |
| `last_observed_at`                 | observed event payload docs                                                        |                      likely yes |                                  yes | observed projector/read not verified                    |
| `last_exhausted_at`                | exhausted event occurred_at / optional observed_at                                 |                         partial |                                  yes | no dashboard aggregate field                            |
| `scheduled_wakeup_at`              | scheduled wakeup `run_after` / `reset_at`                                          |                             yes |                                  yes | ok                                                      |
| `secret API key`                   | should never appear                                                                |                              no |                                   no | keep absent                                             |

CapacityWindow ownership is clear in docs: WorkItem remains passive; CapacityWindow owns provider/account/model reset, wakeup, admission, remaining requests/tokens, active reservations and admitted/skipped work refs.

---

# 7. Snapshot / recovery matrix

| state                         |                                                     targeted read exists |                               can recover after missed event | gap                                                                                                                             |
| ----------------------------- | -----------------------------------------------------------------------: | -----------------------------------------------------------: | ------------------------------------------------------------------------------------------------------------------------------- |
| ClusterGroup rows             | yes: `getDraftClaimClustersByWorkflow` / backend `/draft-claim-clusters` |                                                          yes | reducer must call it after cluster availability or recovery.                                                                    |
| ClusterBatch rows             |                yes, included in cluster read when `include_batches=true` |                                                          yes | only initial batch surfaces; not dynamic work                                                                                   |
| compaction frontier           |                                  yes: `/draft-claim-compaction-frontier` |                                                          yes | current frontend not using it for document-card.                                                                                |
| generated nodes               |                                     yes: `/draft-claim-compaction-nodes` |                                                          yes | should be triggered by `ResultApplied`.                                                                                         |
| pending reduction work        |                           yes, embedded in frontier `pending_work_items` |                                                          yes | no separate window/work scoped endpoint; projection targeted read kind names pending work but API wrapper reads whole frontier. |
| attempt history               |                                        not verified as targeted endpoint |    partially via event replay or old snapshot `llm_attempts` | requires_targeted_endpoint: attempt history by workflow/work_item/dispatch_attempt                                              |
| capacity window current state |                                     not as standalone dashboard endpoint | partially via frontend events replay + frontier pending work | requires_targeted_endpoint: capacity window dashboard/read model                                                                |
| document-card full UI         |                                                      old snapshot exists |                                   yes via bootstrap/recovery | not realtime target; frontend still uses snapshot SSE.                                                                          |
| projection event replay       |                           yes: `/frontend-events` with cursor and stream |                                                          yes | frontend not wired to it.                                                                                                       |

---

# 8. Concrete blockers

| blocker                                                        | severity | evidence                                                                                                                                                          | smallest next action                                                                                      |
| -------------------------------------------------------------- | -------: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Local tree unknown                                             |     high | GitHub cannot run `git status --short` in `/home/haku/crm_bot`                                                                                                    | run mandatory local commands before implementation                                                        |
| Frontend still uses full snapshot stream                       |     high | `KnowledgePage` subscribes to `streamWorkflowLiveState`; wrapper calls `/workflow-live-state/events` and replaces full snapshot.                                  | keep reducer work scoped; do not retire snapshot yet                                                      |
| Projection event stream exists but frontend not using it       |     high | backend has `/frontend-events` and `/frontend-events/stream` with cursor; frontend imports/uses `WorkbenchWorkflowLiveStateResponse`, not frontend event reducer. | add shadow consumer later, after compaction contract is deterministic                                     |
| Legacy `cluster_preview` name exists outside guard allowlist   |     high | `KnowledgeDocumentCard.tsx` stage labels and `previewStage` still use `cluster_preview`.                                                                          | remove/rename legacy UI stage dependency before reducer contract hardening                                |
| Compaction attempt parent currently inferred by string parsing |     high | `_batch_ref_from_work_item_id` strips `claim-compaction:{workflow_run_id}:` prefix.                                                                               | carry explicit `group_ref/batch_ref/input_node_refs` in attempt/prepared payload or rely on targeted read |
| DispatchPrepared payload lacks graph attachment fields         |     high | it has `dispatch_attempt_ids`, `work_item_ids`, generic overlay only.                                                                                             | projection should trigger pending-work targeted read or include safe compaction context                   |
| Capacity dashboard lacks standalone read/current aggregate     |   medium | events expose window facts, frontier exposes pending work, but no dashboard read endpoint verified                                                                | define CapacityWindow dashboard read model later                                                          |
| Active lease release unavailable                               |   medium | leased event exists; release/reservation cleared event not found                                                                                                  | dashboard must compute active leases cautiously or add release event later                                |
| Full reducer not safe yet                                      |     high | event-to-entity mapping has unresolved compaction dynamic work parent issue                                                                                       | next patch should be contract/read/projection readiness, not full reducer                                 |

---

# 9. Option evaluation

| option                                                                         | pros                                          | cons                                                                   | dependencies                      | risk       | decision             |
| ------------------------------------------------------------------------------ | --------------------------------------------- | ---------------------------------------------------------------------- | --------------------------------- | ---------- | -------------------- |
| A: frontend reducer shadow model for compaction only                           | starts real UI migration                      | will encode current parent-key gaps                                    | deterministic event-to-entity map | high       | later                |
| B: backend projection/read contract for compaction graph row generation        | fixes row identity before UI                  | not visible immediately                                                | current projector/read models     | low        | yes                  |
| C: CapacityWindow dashboard backend/read/projection contract                   | valuable operational UI                       | dashboard needs reliable work/window correlation and release semantics | B + capacity aggregation          | medium     | after B/D            |
| D: ClaimBuilder-style attempt append semantics for compaction reducer contract | directly closes retry/attempt history problem | needs explicit parent fields                                           | B                                 | low/medium | yes, together with B |
| E: full frontend reducer for all phases                                        | end goal                                      | too much before compaction deterministic mapping                       | all previous                      | very high  | later                |
| F: curation/publication                                                        | product-visible                               | compaction final active nodes/work state not user-visible yet          | compaction UI closed              | high       | later                |

Recommended next implementation boundary is **B + D**: compaction graph row generation + ClaimBuilder-style attempt append semantics for compaction.

---

# 10. Next implementation prompt skeleton

Ты работаешь в `/home/haku/crm_bot`.

Пиши по-русски.

Задача: Patch 19A — Compaction document-card reducer contract and ClaimBuilder-style attempt append readiness.

Перед изменениями:

1. Выполни:

   * `git status --short`
   * `git log --oneline -10`
2. Если working tree dirty — остановись.
3. Прочитай:

   * `docs/architecture/workflow_frontend_event_projection_map.md`
   * `docs/architecture/capacity_window_refactor_map.md`
   * `src/contexts/knowledge_workbench/observability/application/projectors/draft_claim_compaction_frontend_workflow_event_projector.py`
   * `src/contexts/knowledge_workbench/observability/application/projectors/capacity_window_frontend_workflow_event_projector.py`
   * `src/interfaces/http/knowledge.py`
   * `frontend/src/shared/api/modules/knowledge.ts`

Цель patch:

* Зафиксировать deterministic compaction event-to-entity contract для document-card reducer.
* Dynamic reduction work row keyed by `work_item_id`.
* Attempt history keyed by `dispatch_attempt_id` and appended under `pending_reduction_work[work_item_id]`.
* `DraftClaimCompactionResultApplied` creates generated node availability / frontier change, not just attempt success.
* `DraftClaimCompactionNextWorkScheduled` triggers pending/frontier targeted read and must not create fake ClusterBatch rows.
* CapacityWindow events update `capacity_windows[window_key]` and optionally linked `pending_reduction_work[work_item_id]` through explicit compaction context.
* Do not infer `group_ref` / `batch_ref` through string parsing in frontend reducer contract.

Likely backend contract fixes:

* Ensure compaction attempt/prepared projection payload contains safe explicit attachment fields or targeted read instruction:

  * `workflow_run_id`
  * `group_ref`
  * `batch_ref`
  * `work_item_id`
  * `dispatch_attempt_id`
  * `input_node_refs`
  * `input_claim_refs`
  * `expected_output_kind`
* Keep heavy bodies out of projection payload.
* Keep provider reset / `next_attempt_at` out of WorkItem retry overlay.
* Preserve `work_item_id` as dynamic work row key.

Likely tests:

* projector test for compaction dispatch prepared attachment contract;
* projector test for retryable/terminal attempts appending by `dispatch_attempt_id`;
* projector test that `ResultApplied` exposes generated-node targeted read and does not imply generated nodes on attempt-completed;
* projector test that `NextWorkScheduled` does not create fake ClusterBatch rows;
* architecture guard against `cluster_preview` UI/runtime regression outside explicit allowlist;
* capacity projection test for `compaction_context` linking to pending reduction work.

Do not implement:

* full frontend reducer;
* curation/publication;
* CapacityWindow dashboard UI;
* final embeddings/report;
* old KnowledgeService/chunks;
* fake ClusterBatch rows.

---

## Read-only commands/tools used

Не запускал tests, не создавал `.env.test`, не мутировал файлы.

Через GitHub read-only были выполнены:

```text
fetch_commit main
fetch_file docs/architecture/workflow_frontend_event_projection_map.md
fetch_file docs/architecture/capacity_window_refactor_map.md
search/fetch ClaimBuilder outcome projector
search/fetch Compaction frontend workflow event projector
search/fetch CapacityWindow projector
search/fetch compaction reduction state models/repository/port
fetch_file src/interfaces/http/knowledge.py
fetch_file frontend/src/shared/api/modules/knowledge.ts
fetch_file frontend/src/pages/knowledge/KnowledgePage.tsx
fetch_file frontend/src/pages/knowledge/components/KnowledgeDocumentCard.tsx
```

Итог: **compaction backend/read/projection foundation достаточно близок, но перед frontend reducer нужен Patch 19A contract hardening: explicit row keys, ClaimBuilder-style attempt append semantics, dynamic reduction work rows, CapacityWindow correlation without fake ClusterBatch and without string parsing.**
