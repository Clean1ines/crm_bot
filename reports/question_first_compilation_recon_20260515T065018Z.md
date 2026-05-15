# Question-first compilation recon 20260515T065018Z

## Repository state
```
git status --short:

branch:
work

HEAD:
878dbab652222e3d4a0043bff1bec885b3cc3be9

DATABASE_URL: NOT SET

dirty files:

docs/architecture/crm_bot_domain_map_v1.md: present
frontend/package.json: present
```

## Focused recon notes

- Domain Map present. Relevant contract: Knowledge Compilation produces KnowledgeEnrichment -> EmbeddingText -> RetrievalSurface; retrieval surface is production answer surface, not an artifact dump; evidence/source authority and answer orchestration are separate contexts.
- FAQ prompt previously required embedding_text to include source_excerpt and did not explicitly define one canonical entry as one answer intent / stable information need.
- Preprocessor payload carried previous_answer_titles only; titles were used as cross-chunk identity context, while question samples and answer digest were not carried in a budgeted shortlist.
- Ingestion compiled entries by deterministic answer topic key and later Stage K8 semantic retightening; this means over-merge could already exist before retighten.
- Canonical creation preserves questions/synonyms/tags into KnowledgeEnrichment; repository add/retighten writes enrichment JSONB. Empty values can still persist if upstream LLM output is empty, so the first pipeline layer must generate/preserve metadata.
- DATABASE_URL was NOT SET at initial recon, so optional production DB recon was skipped to avoid relying on unavailable DB state.

## Diagnosis

A. Prompt problem: FAQ and semantic merge instructions were still too title/topic/embedding-text oriented, did not explicitly require replacement canonical answer instead of append, and did not clearly separate same answer intent from related topic words.

B. Payload/context problem: cross-chunk prompt context sent previous titles, not known question intent cards. The LLM did not receive a bounded list of already compiled primary questions/question samples/answer digests.

C. Domain model problem: there was no small typed contract for a known question intent card. questions/synonyms/tags existed on entries but were not first-class compiler identity context.

D. Persistence problem: repository persistence can store enrichment, but it cannot recover metadata that preprocessing failed to generate; upstream empty tuples become empty enrichment.

E. Merge/retighten problem: semantic retighten runs after primary compilation, so it is too late as the main control against snowballing.

F. Retrieval side-effect: ranking/preview can only rank the production retrieval surface it receives; bloated entries without question metadata pollute that surface before SQL ranking is involved.
