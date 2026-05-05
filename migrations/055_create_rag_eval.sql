CREATE TABLE IF NOT EXISTS rag_eval_datasets (
    id TEXT PRIMARY KEY,
    project_id UUID NOT NULL,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'created',
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    model_used TEXT NOT NULL DEFAULT '',
    total_questions INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_rag_eval_datasets_project_document
    ON rag_eval_datasets(project_id, document_id, generated_at DESC);

CREATE TABLE IF NOT EXISTS rag_eval_questions (
    id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES rag_eval_datasets(id) ON DELETE CASCADE,
    project_id UUID NOT NULL,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,

    question TEXT NOT NULL,
    question_type TEXT NOT NULL,
    expected_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    expected_answer_summary TEXT NOT NULL DEFAULT '',

    should_answer BOOLEAN NOT NULL DEFAULT TRUE,
    should_escalate BOOLEAN NOT NULL DEFAULT FALSE,
    difficulty INTEGER NOT NULL DEFAULT 1,
    severity TEXT NOT NULL DEFAULT 'medium',
    source TEXT NOT NULL DEFAULT 'llm_generated',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rag_eval_questions_dataset
    ON rag_eval_questions(dataset_id);

CREATE INDEX IF NOT EXISTS idx_rag_eval_questions_project_document
    ON rag_eval_questions(project_id, document_id);

CREATE INDEX IF NOT EXISTS idx_rag_eval_questions_type
    ON rag_eval_questions(question_type);

CREATE TABLE IF NOT EXISTS rag_eval_runs (
    id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES rag_eval_datasets(id) ON DELETE CASCADE,
    project_id UUID NOT NULL,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,

    status TEXT NOT NULL DEFAULT 'created',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,

    retriever_version TEXT NOT NULL DEFAULT '',
    reranker_version TEXT NOT NULL DEFAULT '',
    generator_model TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_rag_eval_runs_dataset_started
    ON rag_eval_runs(dataset_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_rag_eval_runs_project_document
    ON rag_eval_runs(project_id, document_id, started_at DESC);

CREATE TABLE IF NOT EXISTS rag_eval_results (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES rag_eval_runs(id) ON DELETE CASCADE,
    question_id TEXT NOT NULL REFERENCES rag_eval_questions(id) ON DELETE CASCADE,

    retrieved_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    top1_hit BOOLEAN NOT NULL DEFAULT FALSE,
    top3_hit BOOLEAN NOT NULL DEFAULT FALSE,
    top5_hit BOOLEAN NOT NULL DEFAULT FALSE,
    expected_chunk_found BOOLEAN NOT NULL DEFAULT FALSE,
    wrong_chunk_top1 BOOLEAN NOT NULL DEFAULT FALSE,

    answer_text TEXT NOT NULL DEFAULT '',
    answer_supported BOOLEAN NOT NULL DEFAULT FALSE,
    hallucination_risk TEXT NOT NULL DEFAULT 'medium',
    should_answer_passed BOOLEAN NOT NULL DEFAULT FALSE,

    score DOUBLE PRECISION NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    judge_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    latency_ms INTEGER NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rag_eval_results_run
    ON rag_eval_results(run_id);

CREATE INDEX IF NOT EXISTS idx_rag_eval_results_question
    ON rag_eval_results(question_id);

CREATE INDEX IF NOT EXISTS idx_rag_eval_results_failed
    ON rag_eval_results(run_id)
    WHERE score < 0.75;

CREATE TABLE IF NOT EXISTS rag_quality_reports (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES rag_eval_runs(id) ON DELETE CASCADE,
    dataset_id TEXT NOT NULL REFERENCES rag_eval_datasets(id) ON DELETE CASCADE,
    project_id UUID NOT NULL,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,

    score DOUBLE PRECISION NOT NULL DEFAULT 0,
    readiness TEXT NOT NULL DEFAULT 'not_ready',

    strengths JSONB NOT NULL DEFAULT '[]'::jsonb,
    problems JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    markdown TEXT NOT NULL DEFAULT '',

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rag_quality_reports_project_document
    ON rag_quality_reports(project_id, document_id, created_at DESC);
