
# Provider-agnostic capacity and budget policy model

Status: B0 boundary contract + B1a compatibility map.

This document freezes the boundary model before behavioral refactors. It does not migrate runtime code, token names, segmentation, compaction, capacity storage, or provider execution.

The target pipeline remains provider-agnostic:

upload document
→ choose document segmentation policy
→ segment source into SourceUnits
→ schedule extraction WorkItems
→ choose phase route
→ estimate WorkItem budget
→ ask capacity/admission policy if it can run now
→ execute provider request
→ validate provider/domain outcome
→ decide retry/fallback/split/accept/terminal
→ persist draft claims
→ embed draft claims
→ cluster draft claims
→ build compaction batches
→ compact/reduce/dedupe claims
→ build curation model
→ user publishes
→ generate final retrieval embeddings

The pipeline/domain must not know:

* Groq Free API key count.
* Groq-specific model refs.
* Free-plan TPM values.
* `provider="groq"` as a generic assumption.
* `max_completion_tokens = remaining_tpm - input` as a universal rule.
* Markdown heading segmentation as a universal document rule.
* Compaction active model as a domain constant.
* Fallback/user-choice/special routes as always present.

## 1. Core principle

Groq Free is an exotic provider/deployment profile.

It must be implemented as a provider profile/policy implementation.

It must not define the domain model of Workbench, Execution Runtime, Workflow Runtime, or generic LLM Runtime.

The domain model must describe stable business/runtime concepts: source units, work items, phase outcomes, validation decisions, retry decisions, compaction decisions, and publication. Provider/account/model/free-plan details are deployment facts behind policy implementations.

## 2. Layer ownership

### Workbench / Source domain owns

* `SourceDocument` / `SourceUnit` semantics.
* `DraftClaimObservation` semantics.
* Claim-builder / compaction domain validation.
* Empty claims semantics.
* SourceUnit split as a domain outcome after all viable policy routes fail.
* Phase completion semantics.

### Workbench / Source domain must not own

* Groq model ids.
* Groq provider id.
* Free-plan TPM values.
* Request payload fields.
* `max_completion_tokens`.
* Provider rate-limit headers.
* API key count.
* Route catalog seed details.
* Compaction fit-by-Groq-TPM.

### Policy interfaces own

* Document segmentation choice.
* Phase token budgeting.
* Provider capacity accounting.
* Request output cap calculation.
* Route selection.
* Admission.
* Retry estimate.
* Attempt decision.
* Compaction batching/reduction.
* User-choice behavior.

### Provider/deployment profiles own

* Concrete provider/account/model facts.
* Model rate limits.
* Provider-specific accounting mode.
* Provider-specific output cap requirement.
* Max parallel attempts.
* Wake/sleep strategy.
* Fallback exclusions.

### Runtime mechanisms own

* WorkItem lifecycle.
* Lease/attempt recording.
* Command/outbox/wakeup mechanics.
* Provider HTTP execution.
* Usage mapping.
* Capacity observations/reservations.

## 3. Required policy interfaces

These are target contracts. B0 documents them; it does not require immediate code interfaces unless a tiny marker/protocol already exists and can be added without behavior change.

| Policy                             | Owner bounded context                                                                                   | Input                                                                                            | Output                                                                    | Must not know                                                                                   | Groq Free implementation location                                                         | Future OpenAI/DeepSeek/Local extension point                                     |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `DocumentSegmentationPolicy`       | Workbench source management / document segmentation                                                     | source document metadata, detected format, text, requested preprocessing/segmentation profile    | ordered SourceUnit segmentation plan                                      | provider id, model refs, TPM, API keys, request caps                                            | not in Groq; Groq may only influence later phase budgeting/admission                      | format-specific policies for markdown/pdf/html/plain text without domain changes |
| `SourceUnitSplitPolicy`            | Workbench source management / document segmentation                                                     | failed SourceUnit, failure reason, hard/soft input limits, prior split lineage                   | child SourceUnit plan or terminal split refusal                           | Groq model names, free-plan key count, HTTP payload fields                                      | provider profile may report limits; split policy stays Workbench-owned                    | OpenAI/DeepSeek/Local provide limits/quality ceilings through policy inputs      |
| `PhaseTokenBudgetPolicy`           | LLM Runtime application policy, with phase-specific Workbench adapters                                  | phase, work item kind, prompt profile, source/input estimates, business quality ceilings         | estimated input/output/total budget and quality ceilings                  | provider headers, API keys, concrete free-plan windows                                          | Groq Free profile supplies provider limits/accounting facts behind generic budget inputs  | paid/cost/local profiles supply cost/quality/concurrency limits                  |
| `ProviderCapacityAccountingPolicy` | Capacity Runtime / LLM Runtime capacity boundary                                                        | provider profile, account/window observations, reservations, actual usage                        | available capacity view and reset/wakeup hints                            | Workbench claim semantics, compaction graph semantics                                           | `src/contexts/llm_runtime/infrastructure/providers/groq/` or explicit Groq profile wiring | OpenAI project/org windows, DeepSeek windows, local GPU lanes                    |
| `RequestOutputCapPolicy`           | LLM Runtime application policy                                                                          | route candidate, estimated input, estimated output, remaining capacity, hard limits, safety gaps | `request_output_cap_tokens` or no-cap decision where provider allows it   | Workbench domain decisions, prompt-specific semantic validation                                 | Groq Free combined TPM profile requires explicit cap calculation                          | OpenAI/DeepSeek may cap by cost/quality; local may cap by memory/context         |
| `RouteSelectionPolicy`             | LLM Runtime application policy / provider profile boundary                                              | phase, model capabilities, hard limits, quality ceilings, fallback exclusions, user-choice state | ordered route candidates, possibly empty fallback/special arrays          | Workbench persistence details, SourceUnit storage, API key count unless inside provider profile | Groq profile seeds Groq model route facts and exclusions                                  | OpenAI/DeepSeek/Local route catalogs can be swapped without domain changes       |
| `AdmissionPolicy`                  | Capacity Runtime / LLM Runtime application boundary                                                     | route candidate, estimated budget, capacity view, reservations, schedule state                   | admitted/deferred/paused/rejected decision with reason and wakeup         | claim text semantics, compaction graph details, provider HTTP payload fields                    | Groq Free profile enforces combined TPM and partial-window behavior                       | paid providers add cost/project budgets; local adds GPU lane backpressure        |
| `RetryEstimatePolicy`              | LLM Runtime application policy, with Workbench phase adapters                                           | failed attempt, validation outcome, prior usage, next candidate, source/input estimates          | next estimated budget and safety gaps                                     | provider-specific headers except normalized capacity facts                                      | Groq profile may adjust output gap for free TPM retries                                   | provider-specific retry cost/latency/quality estimates                           |
| `AttemptDecisionPolicy`            | Workbench extraction/compaction policy for domain result; LLM Runtime for provider result normalization | provider result, validation result, capacity result, retry history                               | accept/retry/fallback/split/defer/pause/user-choice/terminal decision     | raw provider headers, API key count, concrete request payload shape                             | Groq Free only contributes normalized capacity/profile facts                              | OpenAI/DeepSeek/Local reuse domain decisions with different profile facts        |
| `CompactionBatchingPolicy`         | Workbench extraction/compaction application policy                                                      | draft claim graph, cluster state, prompt profile, phase budget, quality ceilings                 | compaction work item batches                                              | Groq TPM constants, active Groq model refs, API keys                                            | Groq Free profile only supplies budget constraints through generic inputs                 | batching can become quality/cost/local-lane driven                               |
| `CompactionReductionPolicy`        | Workbench extraction/compaction domain/application policy                                               | compaction comparison results, graph lineage, incompatibility edges, budget fit statuses         | next reduction/rewrite/user-choice/done decision                          | Groq TPM constants, provider id literals, default Groq route catalog                            | no Groq-specific constants in target domain policy                                        | provider profiles only change budget-fit inputs, not graph semantics             |
| `PhaseCompletionPolicy`            | Workbench workflow/saga policy                                                                          | work item statuses, attempts, phase checkpoints, persisted artifacts, validation outcomes        | phase complete/continue/wait/terminal transition                          | provider-specific model ids, headers, key counts                                                | Groq Free cannot define completion semantics                                              | all providers reuse the same phase completion contract                           |
| `UserChoicePolicy`                 | Workbench workflow/application boundary                                                                 | phase state, fallback availability, degraded route candidates, user/project settings             | continue/wait/degraded/terminal user-choice command or no-choice behavior | assumption that fallback/special routes always exist                                            | Groq Free may expose wait-vs-low-quality choice when daily limits are exhausted           | OpenAI/DeepSeek/Local can expose cost/quality/lane choices or none               |

## 4. Token vocabulary contract

Use these terms:

* `estimated_input_tokens`: pre-request estimate for prompt/input/context tokens.
* `estimated_output_tokens`: pre-request estimate for answer/completion tokens.
* `estimated_total_tokens`: pre-request input + output estimate.
* `request_output_cap_tokens`: explicit per-request cap for output tokens.
* `reserved_total_tokens`: total capacity reserved before execution.
* `actual_input_tokens`: provider-reported or mapped input tokens after execution.
* `actual_output_tokens`: provider-reported or mapped output tokens after execution.
* `actual_total_tokens`: actual input + output tokens after execution.
* `hard_input_limit`: provider/model hard input limit.
* `hard_output_limit`: provider/model hard output limit.
* `hard_total_limit`: provider/model hard total request limit.
* `quality_input_ceiling`: soft/business quality ceiling for input size.
* `quality_output_ceiling`: soft/business quality ceiling for output size.
* `safety_gap_tokens`: generic conservative gap where no narrower term exists.
* `request_safety_gap_tokens`: gap used when calculating request output caps.
* `segmentation_safety_gap_tokens`: gap used when deciding source segmentation/split.
* `retry_output_gap_tokens`: extra output gap used for retry/fallback estimates.

Explicit mapping:

prompt_tokens      = input
completion_tokens  = output / answer
total_tokens       = input + output
max_completion_tokens = max output / max answer

`reserved_output_tokens` is a legacy ambiguous symbol and must not be introduced as a new contract. New code must use one of:

* `estimated_output_tokens`
* `request_output_cap_tokens`
* `reserved_total_tokens`
* `segmentation_input_safety_gap_tokens`

depending on the meaning.

## 5. Groq Free profile boundary

### GroqFreeCombinedTpmProfile owns:

* Provider ref `groq`.
* Configured account/org refs.
* Model route catalog seed.
* Combined TPM accounting.
* Explicit `max_completion_tokens` requirement.
* Request output cap policy: `remaining_tpm - estimated_input_tokens - request_safety_gap_tokens`.
* Default `max_parallel_attempts_per_window = 1`.
* Partial-window no-fit behavior.
* Wake/sleep strategy for free limits.
* Daily fallback exclusions.

For Groq Free, partial-window no-fit means that a currently insufficient TPM window does not by itself prove model or route unsuitability. It may only mean that the request should wait for the next capacity window, use a smaller input, use a different policy-approved route, or surface a user choice if policy allows that.

### Groq Free must not leak into:

* Workbench domain.
* Source segmentation domain.
* Compaction domain.
* Generic composition.
* Generic LLM runtime domain.
* Execution Runtime WorkItem entity.
* Workflow Runtime command model.

Required B0 marker: no admitted Groq request without explicit `max_completion_tokens`.

Known current implementation paths to audit in B1b, not fix in B0:

* `groq_dispatch_executor._resolve_max_completion_tokens`
* `groq_chat_request_builder`

## 6. Future provider profiles

### OpenAI paid

OpenAI paid profiles must be possible without changing domain code.

Expected differences:

* Likely one org/project/account rather than four free accounts.
* Parallelism within one account/window matters.
* User/project/phase cost budgets matter.
* Quality ceilings may matter more than hard request limit.
* Request size may be quality-limited, not free-TPM-limited.

### DeepSeek cheap

DeepSeek profiles must be possible without changing domain code.

Expected differences:

* Cost pressure is lower.
* Batching may be quality-driven.
* Provider accounting is still configurable and must not be hardcoded into Workbench semantics.

### Local GPU

Local GPU profiles must be possible without changing domain code.

Expected differences:

* No TPM.
* GPU memory, concurrency, queue depth, and backpressure constraints matter.
* Model execution lanes are not API key windows.

## 7. Non-negotiable invariants

1. No Groq model refs in Workbench domain or compaction domain.
2. No `provider="groq"` literal in generic composition/admission code.
3. No new `reserved_output_tokens` contract.
4. No admitted Groq request without explicit `max_completion_tokens`.
5. No compaction fit-by-Groq-TPM in domain policy.
6. No default_groq route catalog as generic default.
7. Markdown heading segmentation is a DocumentFormat-specific policy, not universal source ingestion.
8. Partial-window input/output-too-large does not prove route/model unsuitability.
9. Fallback/user-choice/special route arrays may be empty.
10. Hard provider limits and soft quality/business limits are separate concepts.

## 8. B1 compatibility map

B1a is a documentation and guard-marker slice only. It does not rename runtime
fields, rewrite payloads, change admission behavior, change request payloads, or
change provider execution.

B1a makes the legacy vocabulary compatibility contract explicit so B1b/B1c/B1d
cannot continue treating `reserved_output_tokens` as a multi-meaning concept.

### Legacy to target mapping

| Legacy symbol / location | Current B0 meaning | Target vocabulary | Migration slice |
| --- | --- | --- | --- |
| legacy `reserved_output_tokens` in segmentation budget | input-side safety gap subtracted from source segment capacity | `segmentation_input_safety_gap_tokens` | B1d or dedicated segmentation vocabulary cleanup after B1a/B1b/B1c |
| legacy `reserved_output_tokens` in claim-builder schedule payload | expected model answer size for the section | `estimated_output_tokens` | B1c |
| legacy `reserved_output_tokens` in admission minimum output | minimum output that must fit the selected capacity window | `estimated_output_tokens` used as `minimum_output_tokens` | B1b/B1c boundary |
| legacy `reserved_output_tokens` in Groq request executor | source used to derive the concrete Groq output cap | `request_output_cap_tokens` / output cap source | B1b |
| legacy `estimated_prompt_tokens` in `LlmTaskCapacityProfile` | estimated prompt/input/context tokens | `estimated_input_tokens` | B1c/B1d compatibility rename |
| legacy `estimated_completion_tokens` in `LlmTaskCapacityProfile` | estimated answer/completion tokens | `estimated_output_tokens` | B1c/B1d compatibility rename |
| legacy `actual_prompt_tokens` in capacity observations | provider-reported input usage | `actual_input_tokens` | compatibility mapping before storage/API rename |
| legacy `actual_completion_tokens` in capacity observations | provider-reported output usage | `actual_output_tokens` | compatibility mapping before storage/API rename |

Required exact compatibility statements:

legacy reserved_output_tokens in segmentation budget → segmentation_input_safety_gap_tokens

legacy reserved_output_tokens in claim-builder schedule payload → estimated_output_tokens

legacy reserved_output_tokens in admission minimum output → estimated_output_tokens used as minimum_output_tokens

legacy reserved_output_tokens in Groq request executor → request_output_cap_tokens / output cap source

legacy estimated_prompt_tokens in LlmTaskCapacityProfile → estimated_input_tokens

legacy estimated_completion_tokens in LlmTaskCapacityProfile → estimated_output_tokens

legacy actual_prompt_tokens in capacity observations → actual_input_tokens

legacy actual_completion_tokens in capacity observations → actual_output_tokens

### B1a target names, documentation only

These names are contract markers for B1 planning. B1a must not implement them as
runtime behavior unless a later slice explicitly changes code and tests:

* `TokenBudgetCompatibilityMap`
* `LegacyTokenBudgetFieldMapping`
* `RequestOutputCapPolicy`
* `RoughTokenEstimator(multiplier)`

### B1b/B1c/B1d split after compatibility map

B1b:

* introduce `RequestOutputCapPolicy`
* forbid admitted Groq request without explicit `max_completion_tokens`
* no runtime uncapped Groq request
* calculate Groq Free `request_output_cap_tokens` from remaining TPM, estimated input, and request safety gap
* if `request_output_cap_tokens < estimated_output_tokens`, the WorkItem does not fit this window
* if `request_output_cap_tokens <= 0`, do not send request

B1c:

* migrate claim-builder schedule payload from `reserved_output_tokens` to `estimated_output_tokens`
* keep compatibility read for old payloads if needed
* stop using `reserved_output_tokens` as the claim-builder expected output estimate

B1d:

* introduce single `RoughTokenEstimator(multiplier)`
* claim_builder multiplier target 3.7
* compaction multiplier target 3.3
* remove chars/3.3, chars/4, chars/4+40 drift

B1a success criteria:

* the compatibility map exists
* the guard test asserts the compatibility map exists
* no runtime behavior changes
* no DB migrations
* no provider API calls
* no claim that `reserved_output_tokens` or `max_completion_tokens` is fixed


## 9. B1 roadmap, explicitly split

B1a: vocabulary contract + compatibility mapping, no behavior change
B1b: request output cap policy, no admitted uncapped Groq requests
B1c: claim-builder estimate rename/split
B1d: estimator unification

Anti-goals:

Do not implement durable CapacityWindow before B1a/B1b.
Do not rewrite compaction before B1a/B1b/B1c.
Do not move route catalog before boundary guard markers exist.

B0 only freezes boundaries and known leaks so that B1 can start safely. It does not claim that Groq Free leakage is fixed.
