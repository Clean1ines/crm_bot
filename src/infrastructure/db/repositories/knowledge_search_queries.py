"""SQL query constants for Workbench runtime knowledge retrieval searches."""

# Keep SQL text out of KnowledgeRepository so repository methods own orchestration,
# while this module owns large query bodies.

_RUNTIME_ENTRY_SELECT = """
    entry.runtime_entry_id AS id,
    entry.project_id::text AS project_id,
    entry.claim AS content,
    entry.source_document_ref AS document_id,
    entry.source_document_ref AS source,
    entry.status AS document_status,
    COALESCE(NULLIF(entry.claim_kind, ''), 'faq_workbench_fact') AS entry_kind,
    entry.granularity,
    entry.curation_item_ref,
    entry.exclusion_scope,
    entry.evidence_block,
    entry.triples,
    NULL::text AS title,
    CASE
        WHEN jsonb_typeof(entry.source_refs) = 'array'
        THEN entry.source_refs
        WHEN jsonb_typeof(entry.source_refs->'source_refs') = 'array'
        THEN entry.source_refs->'source_refs'
        ELSE '[]'::jsonb
    END AS source_refs,
    entry.source_refs AS raw_source_refs,
    entry.source_claim_refs,
    entry.embedding_text,
    entry.possible_questions AS questions,
    '[]'::jsonb AS synonyms,
    '[]'::jsonb AS tags,
    (
        COALESCE(entry.embedding_text, '')
        || ' '
        || COALESCE(entry.claim, '')
        || ' '
        || COALESCE(questions_text.value, '')
        || ' '
        || COALESCE(questions_text.value, '')
        || ' '
        || COALESCE(entry.triples::text, '')
        || ' '
        || COALESCE(NULLIF(entry.evidence_block, ''), '')
    ) AS search_text
"""

_RUNTIME_ENTRY_FROM = """
FROM knowledge_workbench_runtime_retrieval_entries AS entry
JOIN knowledge_workbench_runtime_retrieval_entry_embeddings AS emb
  ON emb.runtime_entry_id = entry.runtime_entry_id
LEFT JOIN LATERAL (
    SELECT string_agg(question_text.value, ' ') AS value
    FROM jsonb_array_elements_text(entry.possible_questions) AS question_text(value)
) AS questions_text ON TRUE
"""

_RUNTIME_ENTRY_WHERE = """
WHERE entry.project_id = $2::uuid
  AND entry.visibility = 'published'
  AND entry.status = 'active'
  AND emb.embedding_model_id IS NOT NULL
  AND emb.embedding IS NOT NULL
"""

RUNTIME_VECTOR_SEARCH_SQL = f"""
SELECT
{_RUNTIME_ENTRY_SELECT},
    (1 - (emb.embedding <=> $1::vector)) AS vector_score,
    0.0::double precision AS lexical_score,
    0.0::double precision AS exact_score
{_RUNTIME_ENTRY_FROM}
{_RUNTIME_ENTRY_WHERE}
  AND $4::text[] IS NOT NULL
  AND emb.embedding_model_id = $5
  AND emb.dimensions = $6
ORDER BY emb.embedding <=> $1::vector
LIMIT $3
"""


RUNTIME_HYBRID_SEARCH_SQL = f"""
WITH q AS (
    SELECT
        $1::vector AS query_embedding,
        websearch_to_tsquery('russian', $2) AS query_ts,
        lower($2) AS query_text
),
base AS (
    SELECT
{_RUNTIME_ENTRY_SELECT},
        emb.embedding
{_RUNTIME_ENTRY_FROM}
{_RUNTIME_ENTRY_WHERE.replace("$2::uuid", "$3::uuid")}
      AND $6::text[] IS NOT NULL
      AND emb.embedding_model_id = $7
      AND emb.dimensions = $8
),
vector_candidates AS (
    SELECT
        base.*,
        (1 - (base.embedding <=> q.query_embedding)) AS vector_score,
        row_number() OVER (ORDER BY base.embedding <=> q.query_embedding) AS vector_rank
    FROM base, q
    ORDER BY base.embedding <=> q.query_embedding
    LIMIT $4
),
lexical_candidates AS (
    SELECT
        base.*,
        ts_rank_cd(
            to_tsvector('russian', COALESCE(base.search_text, '')),
            q.query_ts
        ) AS lexical_score,
        row_number() OVER (
            ORDER BY ts_rank_cd(
                to_tsvector('russian', COALESCE(base.search_text, '')),
                q.query_ts
            ) DESC
        ) AS lexical_rank
    FROM base, q
    WHERE to_tsvector('russian', COALESCE(base.search_text, '')) @@ q.query_ts
    ORDER BY lexical_score DESC
    LIMIT $4
),
candidates AS (
    SELECT
        id,
        project_id,
        content,
        document_id,
        source,
        document_status,
        entry_kind,
        granularity,
        curation_item_ref,
        exclusion_scope,
        evidence_block,
        triples,
        title,
        source_refs,
        raw_source_refs,
        source_claim_refs,
        embedding_text,
        questions,
        synonyms,
        tags,
        search_text,
        vector_score,
        0.0::double precision AS lexical_score,
        vector_rank,
        NULL::bigint AS lexical_rank
    FROM vector_candidates

    UNION ALL

    SELECT
        id,
        project_id,
        content,
        document_id,
        source,
        document_status,
        entry_kind,
        granularity,
        curation_item_ref,
        exclusion_scope,
        evidence_block,
        triples,
        title,
        source_refs,
        raw_source_refs,
        source_claim_refs,
        embedding_text,
        questions,
        synonyms,
        tags,
        search_text,
        0.0::double precision AS vector_score,
        lexical_score,
        NULL::bigint AS vector_rank,
        lexical_rank
    FROM lexical_candidates
),
merged AS (
    SELECT
        id,
        max(project_id) AS project_id,
        max(content) AS content,
        max(document_id) AS document_id,
        max(source) AS source,
        max(document_status) AS document_status,
        max(entry_kind) AS entry_kind,
        max(granularity) AS granularity,
        max(curation_item_ref) AS curation_item_ref,
        max(exclusion_scope) AS exclusion_scope,
        max(evidence_block) AS evidence_block,
        (jsonb_agg(triples)->0) AS triples,
        max(title) AS title,
        (jsonb_agg(source_refs)->0) AS source_refs,
        (jsonb_agg(raw_source_refs)->0) AS raw_source_refs,
        (jsonb_agg(source_claim_refs)->0) AS source_claim_refs,
        max(embedding_text) AS embedding_text,
        (jsonb_agg(questions)->0) AS questions,
        (jsonb_agg(synonyms)->0) AS synonyms,
        (jsonb_agg(tags)->0) AS tags,
        max(search_text) AS search_text,
        max(vector_score) AS vector_score,
        max(lexical_score) AS lexical_score,
        min(vector_rank) AS vector_rank,
        min(lexical_rank) AS lexical_rank
    FROM candidates
    GROUP BY id
)
SELECT
    id,
    project_id,
    content,
    document_id,
    source,
    document_status,
    entry_kind,
    granularity,
    curation_item_ref,
    exclusion_scope,
    evidence_block,
    triples,
    title,
    source_refs,
    raw_source_refs,
    source_claim_refs,
    embedding_text,
    questions,
    synonyms,
    tags,
    search_text,
    vector_score,
    lexical_score,
    CASE
        WHEN lower(search_text) LIKE ('%' || (SELECT query_text FROM q) || '%')
        THEN 1.0
        ELSE 0.0
    END AS exact_score
FROM merged
ORDER BY (
    COALESCE(vector_score, 0.0) * 0.72
    + LEAST(COALESCE(lexical_score, 0.0), 1.0) * 0.18
    + CASE
        WHEN lower(search_text) LIKE ('%' || (SELECT query_text FROM q) || '%')
        THEN 0.10
        ELSE 0.0
      END
) DESC
LIMIT $5
"""


RUNTIME_PREVIEW_SEARCH_SQL = """
WITH q AS (
    SELECT
        websearch_to_tsquery('russian', $1) AS query_ts,
        lower($1) AS query_text
),
base AS (
    SELECT
        entry.runtime_entry_id AS id,
        entry.project_id::text AS project_id,
        entry.claim AS content,
        entry.source_document_ref AS document_id,
        entry.source_document_ref AS source,
        entry.status AS document_status,
        COALESCE(NULLIF(entry.claim_kind, ''), 'faq_workbench_fact') AS entry_kind,
        entry.granularity,
        entry.curation_item_ref,
        entry.exclusion_scope,
        entry.evidence_block,
        entry.triples,
        NULL::text AS title,
        CASE
            WHEN jsonb_typeof(entry.source_refs) = 'array'
            THEN entry.source_refs
            WHEN jsonb_typeof(entry.source_refs->'source_refs') = 'array'
            THEN entry.source_refs->'source_refs'
            ELSE '[]'::jsonb
        END AS source_refs,
        entry.source_refs AS raw_source_refs,
        entry.source_claim_refs,
        entry.embedding_text,
        entry.possible_questions AS questions,
        '[]'::jsonb AS synonyms,
        '[]'::jsonb AS tags,
        (
            COALESCE(entry.embedding_text, '')
            || ' '
            || COALESCE(entry.claim, '')
            || ' '
            || COALESCE(questions_text.value, '')
            || ' '
            || COALESCE(questions_text.value, '')
            || ' '
            || COALESCE(entry.triples::text, '')
            || ' '
            || COALESCE(NULLIF(entry.evidence_block, ''), '')
        ) AS search_text
    FROM knowledge_workbench_runtime_retrieval_entries AS entry
    JOIN knowledge_workbench_runtime_retrieval_entry_embeddings AS emb
      ON emb.runtime_entry_id = entry.runtime_entry_id
    LEFT JOIN LATERAL (
        SELECT string_agg(question_text.value, ' ') AS value
        FROM jsonb_array_elements_text(entry.possible_questions) AS question_text(value)
    ) AS questions_text ON TRUE,
    q
    WHERE entry.project_id = $2::uuid
      AND entry.visibility = 'published'
      AND entry.status = 'active'
      AND emb.embedding_model_id IS NOT NULL
      AND emb.embedding IS NOT NULL
      AND $4::text[] IS NOT NULL
),
scored AS (
    SELECT
        base.*,
        ts_rank_cd(
            to_tsvector('russian', COALESCE(base.search_text, '')),
            q.query_ts
        ) AS lexical_score,
        (
            SELECT COUNT(DISTINCT token)::double precision
            FROM regexp_split_to_table(q.query_text, '[^[:alnum:]а-яё]+') AS token
            WHERE length(token) >= 4
              AND lower(base.search_text) LIKE '%' || token || '%'
        ) AS token_overlap
    FROM base, q
)
SELECT
    id,
    project_id,
    content,
    document_id,
    source,
    document_status,
    entry_kind,
    granularity,
    curation_item_ref,
    exclusion_scope,
    evidence_block,
    triples,
    title,
    source_refs,
    raw_source_refs,
    source_claim_refs,
    embedding_text,
    questions,
    synonyms,
    tags,
    search_text,
    0.0::double precision AS vector_score,
    lexical_score,
    0.0::double precision AS exact_score,
    (
        lexical_score
        + (token_overlap * 0.06)
        + CASE
            WHEN COALESCE(title, '') <> ''
            THEN 0.05::double precision
            ELSE 0.0::double precision
          END
    ) AS score
FROM scored
WHERE lexical_score > 0.0
   OR token_overlap > 0.0
ORDER BY score DESC
LIMIT $3
"""
