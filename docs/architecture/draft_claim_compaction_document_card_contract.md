# Draft Claim Compaction Document-card Contract

## 1. Current checked commit / patch baseline

```text
main baseline: acdcdb4c5c9ad197706a0efb41743bceec368fd8
Patch 17E: ClaimBuilder attempt outcome visibility
Patch 18A: DraftClaimObservation document-card rows
Patch 18B: DraftClaimClusterGroup / ClusterBatch row availability
Patch 18C: DraftClaimCompaction visibility + generated-node targeted read
Patch 18D: active frontier + origin_set + origin-level separation correctness
Patch 18E: compaction frontier read contract
Patch 18F: compaction CapacityWindow correlation
Patch 19A: compaction document-card reducer contract and ClaimBuilder-style attempt append readiness
Patch 19B: frontend projection-event client + pure compaction shadow reducer foundation

Patch 19A is a backend/projection/read-contract + docs + guards patch. It does not implement React reducer, React UI, projection stream consumer, SSE replacement, curation, publication, cross-cluster triple reconciliation, or CapacityWindow dashboard UI.

2. Non-negotiable statements
ClusterBatch is an initial batch surface only.
Dynamic reduction work is not a fake ClusterBatch.
Dynamic reduction work row key is work_item_id.
Attempt history key is dispatch_attempt_id.
Attempts append under pending_reduction_work[work_item_id].
ResultApplied is generated-node/frontier availability, not merely attempt success.
NextWorkScheduled triggers pending/frontier targeted read, not fake batch creation.
CapacityWindow owns reset/admission timing.
Capacity dashboard is a separate future surface.
Pure frontend shadow reducer foundation exists after Patch 19B.
Projection stream hookup into KnowledgePage is later.
Visible React UI/data-source switch is later.
Curation/publication are later.

Projection payloads may expose safe attachment fields:

workflow_run_id
group_ref
batch_ref
work_item_id
dispatch_attempt_id
input_node_refs
input_claim_refs
targeted_read.kind
targeted_read.params

Projection payloads must not expose heavy generated bodies, raw provider response, secret account/API data, claim body, evidence body, or provider reset as WorkItem retry overlay.

3. Table 1 — ClaimBuilder vs Compaction
concern	ClaimBuilder current behavior	Compaction current behavior	Target compaction behavior	Gap / status after Patch 19A
artifact row identity	SourceUnit surface anchors work overlay and attempts.	ClusterGroup, initial ClusterBatch, frontier nodes, pending work, attempts and capacity windows are distinct.	Explicit entity keys, not one parent row.	Contract documented and projected.
attempt identity	dispatch_attempt_id.	dispatch_attempt_id exists on compaction attempts.	compaction_attempts[dispatch_attempt_id].	Hardened.
retry append	Retry attempts append under same WorkItem.	Retryable compaction attempt existed but graph parent was ambiguous.	Append under pending_reduction_work[work_item_id].	Hardened.
generated artifact availability	Successful ClaimBuilder exposes DraftClaimObservation rows by targeted read.	Compaction attempt completed is not generated-node availability.	ResultApplied is generated-node/frontier boundary.	Hardened.
targeted read after result	Draft claim row endpoint.	Compaction nodes/frontier endpoints.	ResultApplied and NextWorkScheduled trigger targeted reads.	Hardened.
capacity overlay	WorkItem/attempt can receive capacity overlay.	Patch 18F added compaction_context.	Capacity events update capacity_windows[window_key] and linked pending work.	Hardened.
pending work visibility	SourceUnit/WorkItem lane.	Frontier read exposes pending reduction work rows.	pending_reduction_work[work_item_id].	Hardened.
dynamic next work	SourceUnit anchored.	Generated nodes can create next work.	NextWorkScheduled triggers pending/frontier read.	Hardened.
cluster/group parent row	SourceUnit is primary parent.	ClusterGroup is high-level parent; ClusterBatch is initial surface.	Dynamic work is not forced into ClusterBatch.	Hardened.
row completion	Completed attempt exposes claims.	Attempt success is not node graph mutation.	ResultApplied mutates generated node/frontier surface.	Hardened.
timeline/history	Attempt history append/update.	Compaction needed explicit append contract.	Append-only by dispatch_attempt_id.	Hardened.
heavy body guard	Heavy rows by targeted read.	Heavy compaction bodies already guarded.	Keep bodies behind targeted reads.	Hardened.
4. Table 2 — Frontend entity model
entity	key	surface / overlay / history	created by	updated by	targeted read	status after Patch 19A
cluster_groups[group_ref]	group_ref	surface	clusters built + targeted read	compaction progress/events	draft_claim_clusters_by_workflow	existing
cluster_batches[batch_ref]	batch_ref	initial surface	cluster targeted read	initial compaction overlay only	draft_claim_clusters_by_workflow	initial only
compaction_frontier_nodes[node_ref]	node_ref	surface	frontier/nodes read; ResultApplied	frontier changes	draft_claim_compaction_nodes_by_workflow_or_group, draft_claim_compaction_frontier_by_workflow_or_group	hardened
pending_reduction_work[work_item_id]	work_item_id	surface + overlay	dispatch prepared / frontier read	attempt/capacity/next-work events	draft_claim_compaction_pending_work_by_workflow_or_group	hardened
compaction_attempts[dispatch_attempt_id]	dispatch_attempt_id	append-only history	dispatch prepared / attempt event	attempt outcome	event stream, future attempt read	hardened
capacity_windows[window_key]	window_key	overlay/future surface	capacity events	capacity events	future dashboard read	source model hardened
5. Table 3 — Compaction event action map
projection_type	action	entity key	parent key	append/update/create	targeted read	status after Patch 19A
workflow_draft_claim_clusters_built	load cluster groups/batches	group_ref, batch_ref	workflow	create	cluster targeted read	existing
workflow_draft_claim_compaction_dispatch_batch_prepared	expose pending work + attempt rows	work_item_id, dispatch_attempt_id	group/batch if known	create/update + append attempt shell	pending/frontier reads	hardened
workflow_draft_claim_compaction_attempt_completed	append completed attempt outcome	dispatch_attempt_id	work_item_id	append/update	no generated-node read	hardened
workflow_draft_claim_compaction_attempt_retryable_failed	append retryable attempt outcome	dispatch_attempt_id	work_item_id	append/update	none	hardened
workflow_draft_claim_compaction_attempt_terminal_failed	append terminal attempt outcome	dispatch_attempt_id	work_item_id	append/update	none	hardened
workflow_draft_claim_compaction_result_applied	generated nodes/frontier available	node_ref via read	group/work item	create/update	nodes + frontier reads	hardened
workflow_draft_claim_compaction_next_work_scheduled	pending dynamic work may exist	work_item_id via read	group	create/update from read	pending + frontier reads	hardened
workflow_capacity_window_*	capacity overlay	window_key, optional work_item_id	capacity/pending work	update	pending work read	hardened
6. Table 4 — Attempt append semantics
case	ClaimBuilder behavior	Compaction target behavior	current support	status after Patch 19A
dispatch prepared	attempt shell exists	append attempt shell under pending work	dispatch ids existed	explicit contexts/targeted read
leased/admitted	capacity overlay on work/attempt	capacity links window to pending work	compaction_context existed	source model hardened
provider completed	attempt outcome	compaction attempt outcome	existed	append contract hardened
validation failed retryable	retry attempt history	append retryable attempt	existed	hardened
terminal failed	terminal attempt history	append terminal attempt	existed	hardened
result applied	generated rows become available	generated nodes/frontier become available	existed	boundary hardened
retry creates next attempt	new dispatch attempt appended	same under pending_reduction_work[work_item_id]	keys existed	hardened
7. Table 5 — CapacityWindow dashboard source model
field	source/event/read model	available now	safe for frontend	status / gap
window_key	capacity events	yes	yes	available
provider	capacity events	yes	yes	available
account_ref	capacity events	yes	yes, safe ref only	no API keys
model_ref	capacity events	yes	yes	available
remaining_minute_requests	observed capacity event	yes	yes	future dashboard
remaining_minute_tokens	observed capacity event	yes	operational	future dashboard
remaining_daily_requests	observed capacity event	yes	yes	future dashboard
remaining_daily_tokens	observed capacity event	yes	operational	future dashboard
reset_at	exhausted/wakeup events	yes	yes	countdown computed frontend
active_lease_count	event aggregation/future read	partial	yes	later
waiting_work_count	frontier pending summary	yes	yes	workflow/group scoped
leased_work_items	leased event + pending read	partial	yes	release event later
blocked_work_items	pending work read	yes	yes	workflow/group scoped
secrets/API keys	none	no	no	forbidden
8. Table 6 — Snapshot/recovery matrix
state	targeted read exists	can recover after missed event	gap / later work
ClusterGroup/ClusterBatch rows	yes	yes	reducer later
compaction frontier	yes	yes	reducer later
generated nodes	yes	yes	reducer later
pending reduction work	yes, through frontier read	yes	optional dedicated endpoint later
attempt history	event replay / snapshot today	partial	targeted attempt history later if needed
capacity window current state	event replay / snapshot today	partial	dashboard read later
9. What remains later
KnowledgePage projection stream hookup
shadow parity/debug comparison with old workflow-live-state
visible React document-card data-source switch
CapacityWindow dashboard UI
projection stream consumer in KnowledgePage
curation/publication
cross-cluster triple reconciliation
10. Forbidden shortcuts
Do not invent fake ClusterBatch rows for dynamic work.
Do not treat attempt completed as generated node availability.
Do not create generated node rows before ResultApplied.
Do not derive reducer parent graph only from work_item_id string parsing.
Do not put provider reset into WorkItem retry overlay.
Do not put heavy generated bodies into projection payload.
Do not replace full frontend with reducer in this patch.
Do not touch curation/publication.

## 11. Patch 19B — Frontend projection-event client + pure shadow reducer foundation

Patch 19B starts the frontend-side preparation for the event-to-entity reducer path.

Implemented frontend-side foundation:

```text
frontend_workflow_event envelope
→ typed frontend client
→ idempotent event-to-entity patch
→ pure DraftClaimCompaction shadow reducer state
→ targeted read requests / recovery hints

Patch 19B adds:

FrontendWorkflowEventEnvelope
FrontendWorkflowEventsResponse
FrontendWorkflowEventsQuery
getFrontendWorkflowEvents(...)
streamFrontendWorkflowEvents(...)
createEmptyCompactionShadowState()
reduceCompactionProjectionEvent(...)

Patch 19B shadow reducer state uses the same entity keys as Patch 19A:

cluster_groups[group_ref]
cluster_batches[batch_ref]
compaction_frontier_nodes[node_ref]
pending_reduction_work[work_item_id]
compaction_attempts[dispatch_attempt_id]
capacity_windows[window_key]

Patch 19B reducer rules:

idempotency is by projection_event_id
attempt rows are deduped by dispatch_attempt_id
retry attempts append under pending_reduction_work[work_item_id]
AttemptCompleted must not create generated frontier nodes
ResultApplied marks generated nodes/frontier dirty and requests targeted reads
NextWorkScheduled requests pending/frontier targeted reads and must not create fake ClusterBatch rows
capacity events update capacity_windows[window_key]
capacity events with compaction_context, work_item_id or dispatch_attempt_id can link pending work and attempts
provider reset remains CapacityWindow-owned and must not become WorkItem retry overlay

Patch 19B deliberately does not connect the projection stream to KnowledgePage.
It also does not change KnowledgeDocumentCard rendering and does not remove workflow-live-state.

Remaining later:

KnowledgePage projection stream hookup
shadow parity/debug comparison with old workflow-live-state
visible DocumentCard data-source switch
CapacityWindow dashboard UI
curation/publication
cross-cluster triple reconciliation