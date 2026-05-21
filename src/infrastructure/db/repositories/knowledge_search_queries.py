"""SQL query constants for knowledge retrieval surface searches."""

# Keep SQL text out of KnowledgeRepository so repository methods own orchestration,
# while this module owns large query bodies.

RUNTIME_VECTOR_SEARCH_SQL = """
                    SELECT
                        rs.entry_id AS id,
                        rs.answer AS content,
                        rs.document_id,
                        d.file_name AS source,
                        d.status AS document_status,
                        rs.entry_kind,
                        rs.title,
                        rs.source_refs,
                        rs.embedding_text,
                        rs.enrichment->'questions' AS questions,
                        rs.enrichment->'synonyms' AS synonyms,
                        rs.enrichment->'tags' AS tags,
                        rs.search_text,
                        (1 - (rs.embedding <=> $1::vector)) AS vector_score,
                        0.0::double precision AS lexical_score,
                        0.0::double precision AS exact_score
                    FROM knowledge_retrieval_surface AS rs
                    LEFT JOIN knowledge_documents AS d ON d.id = rs.document_id
                    WHERE rs.project_id = $2
                      AND rs.embedding IS NOT NULL
                      AND rs.entry_kind = ANY($4::text[])
                      AND rs.status = 'published'
                      AND rs.visibility = 'runtime'
                      AND (d.status = 'processed' OR d.status IS NULL)
                    ORDER BY rs.embedding <=> $1::vector
                    LIMIT $3
                    """

RUNTIME_HYBRID_SEARCH_SQL = """
                    WITH q AS (
                        SELECT
                            $1::vector AS query_embedding,
                            websearch_to_tsquery('russian', $2) AS query_ts,
                            lower($2) AS query_text
                    ),
                    base AS (
                        SELECT
                            rs.entry_id AS id,
                            rs.answer AS content,
                            rs.document_id,
                            d.file_name AS source,
                            d.status AS document_status,
                            rs.entry_kind,
                            rs.title,
                            rs.source_refs,
                            rs.embedding_text,
                            rs.enrichment->'questions' AS questions,
                            rs.enrichment->'synonyms' AS synonyms,
                            rs.enrichment->'tags' AS tags,
                            rs.search_text,
                            rs.embedding
                        FROM knowledge_retrieval_surface AS rs
                        LEFT JOIN knowledge_documents AS d ON d.id = rs.document_id
                        WHERE rs.project_id = $3
                          AND rs.embedding IS NOT NULL
                          AND rs.entry_kind = ANY($6::text[])
                          AND rs.status = 'published'
                          AND rs.visibility = 'runtime'
                          AND (d.status = 'processed' OR d.status IS NULL)
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
                            max(document_id::text)::uuid AS document_id,
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
                scored AS (
                    SELECT
                        rs.entry_id AS id,
                        rs.answer AS content,
                        rs.document_id,
                        d.file_name AS source,
                        d.status AS document_status,
                        rs.entry_kind,
                        rs.title,
                        rs.source_refs,
                        rs.embedding_text,
                        rs.enrichment->'questions' AS questions,
                        rs.enrichment->'synonyms' AS synonyms,
                        rs.enrichment->'tags' AS tags,
                        rs.search_text,
                        ts_rank_cd(
                            to_tsvector('russian', COALESCE(rs.search_text, '')),
                            q.query_ts
                        ) AS lexical_score,
                        (
                            SELECT COUNT(DISTINCT token)::double precision
                            FROM regexp_split_to_table(q.query_text, '[^[:alnum:]а-яё]+') AS token
                            WHERE length(token) >= 4
                              AND lower(rs.search_text) LIKE '%' || token || '%'
                        ) AS token_overlap
                    FROM knowledge_retrieval_surface AS rs
                    LEFT JOIN knowledge_documents AS d ON d.id = rs.document_id,
                    q
                    WHERE rs.project_id = $2
                      AND rs.entry_kind = ANY($4::text[])
                      AND rs.status = 'published'
                      AND rs.visibility = 'runtime'
                      AND (d.status = 'processed' OR d.status IS NULL)
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
