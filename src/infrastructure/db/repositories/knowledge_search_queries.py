"""SQL query constants for Workbench runtime knowledge retrieval searches."""

# Keep SQL text out of KnowledgeRepository so repository methods own orchestration,
# while this module owns large query bodies.

_RUNTIME_ENTRY_SELECT = """
    entry.runtime_entry_id AS id,
    entry.claim AS content,
    entry.source_refs->>'source_document_ref' AS document_id,
    entry.source_refs->>'source_document_ref' AS source,
    entry.status AS document_status,
    COALESCE(NULLIF(fact.claim_kind, ''), 'faq_workbench_fact') AS entry_kind,
    NULL::text AS title,
    entry.source_refs->'source_claim_refs' AS source_refs,
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
        || COALESCE(NULLIF(fact.exclusion_scope, ''), '')
        || ' '
        || COALESCE(NULLIF(evidence.evidence_block, ''), '')
    ) AS search_text
"""

_RUNTIME_ENTRY_FROM = """
FROM knowledge_workbench_runtime_retrieval_entries AS entry
JOIN knowledge_workbench_runtime_retrieval_entry_embeddings AS emb
  ON emb.runtime_entry_id = entry.runtime_entry_id
JOIN knowledge_workbench_canonical_facts AS fact
  ON fact.fact_id = entry.fact_id
LEFT JOIN LATERAL (
    SELECT string_agg(question_text.value, ' ') AS value
    FROM jsonb_array_elements_text(entry.possible_questions) AS question_text(value)
) AS questions_text ON TRUE
LEFT JOIN LATERAL (
    SELECT string_agg(NULLIF(mention.evidence_block, ''), E'\\n') AS evidence_block
    FROM knowledge_workbench_fact_mentions AS mention
    WHERE mention.fact_id = entry.fact_id
) AS evidence ON TRUE
"""

_RUNTIME_ENTRY_WHERE = """
WHERE entry.project_id = $2::uuid
  AND entry.visibility = 'published'
  AND entry.status = 'active'
  AND fact.status = 'published'
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
        content,
        document_id,
        source,
        document_status,
        entry_kind,
        title,
        source_refs,
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
        content,
        document_id,
        source,
        document_status,
        entry_kind,
        title,
        source_refs,
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
        max(content) AS content,
        max(document_id) AS document_id,
        max(source) AS source,
        max(document_status) AS document_status,
        max(entry_kind) AS entry_kind,
        max(title) AS title,
        (jsonb_agg(source_refs)->0) AS source_refs,
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
    content,
    document_id,
    source,
    document_status,
    entry_kind,
    title,
    source_refs,
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
        entry.claim AS content,
        entry.source_refs->>'source_document_ref' AS document_id,
        entry.source_refs->>'source_document_ref' AS source,
        entry.status AS document_status,
        COALESCE(NULLIF(fact.claim_kind, ''), 'faq_workbench_fact') AS entry_kind,
        NULL::text AS title,
        entry.source_refs->'source_claim_refs' AS source_refs,
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
            || COALESCE(NULLIF(fact.exclusion_scope, ''), '')
            || ' '
            || COALESCE(NULLIF(evidence.evidence_block, ''), '')
        ) AS search_text
    FROM knowledge_workbench_runtime_retrieval_entries AS entry
    JOIN knowledge_workbench_canonical_facts AS fact
      ON fact.fact_id = entry.fact_id
    LEFT JOIN LATERAL (
        SELECT string_agg(question_text.value, ' ') AS value
        FROM jsonb_array_elements_text(entry.possible_questions) AS question_text(value)
    ) AS questions_text ON TRUE
    LEFT JOIN LATERAL (
        SELECT string_agg(NULLIF(mention.evidence_block, ''), E'\\n') AS evidence_block
        FROM knowledge_workbench_fact_mentions AS mention
        WHERE mention.fact_id = entry.fact_id
    ) AS evidence ON TRUE,
    q
    WHERE entry.project_id = $2::uuid
      AND entry.visibility = 'published'
      AND entry.status = 'active'
      AND fact.status = 'published'
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
    content,
    document_id,
    source,
    document_status,
    entry_kind,
    title,
    source_refs,
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
