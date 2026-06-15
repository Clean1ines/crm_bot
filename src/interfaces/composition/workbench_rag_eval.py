from __future__ import annotations

from src.contexts.embedding_runtime.infrastructure.composition.embedding_generation_provider_factory import (
    make_embedding_generation_port,
)
from src.contexts.embedding_runtime.infrastructure.config.embedding_runtime_settings import (
    load_embedding_runtime_settings,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.promoted_question_runtime_embedding_text_builder import (
    PromotedQuestionRuntimeEmbeddingTextBuilder,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.apply_workbench_rag_eval_promotion import (
    ApplyWorkbenchRagEvalPromotion,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.run_workbench_rag_eval import (
    RunWorkbenchRagEval,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.llm.workbench_rag_eval_question_generator import (
    WORKBENCH_RAG_EVAL_QUESTION_PROMPT_VERSION,
    WorkbenchRagEvalQuestionGenerator,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.postgres_workbench_rag_eval_repository import (
    PostgresWorkbenchRagEvalRepository,
)
from src.contexts.knowledge_workbench.retrieval.application.use_cases.search_published_workbench_runtime import (
    SearchPublishedWorkbenchRuntime,
)
from src.contexts.knowledge_workbench.retrieval.infrastructure.postgres.postgres_published_workbench_retrieval_repository import (
    PostgresPublishedWorkbenchRetrievalRepository,
)
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutorPort,
)


def make_run_workbench_rag_eval(
    *,
    pool: object,
    llm_dispatch_executor: LlmDispatchExecutorPort,
) -> RunWorkbenchRagEval:
    embedding_settings = load_embedding_runtime_settings()
    question_generator = WorkbenchRagEvalQuestionGenerator.from_prompt_file(
        llm_dispatch_executor=llm_dispatch_executor,
    )
    return RunWorkbenchRagEval(
        rag_eval_repository=PostgresWorkbenchRagEvalRepository(pool),
        question_generator=question_generator,
        search_published_workbench_runtime=SearchPublishedWorkbenchRuntime(
            published_retrieval_port=PostgresPublishedWorkbenchRetrievalRepository(
                pool
            ),
            embedding_generation_port=make_embedding_generation_port(
                embedding_settings
            ),
            embedding_model_id=embedding_settings.local_model,
            embedding_dimensions=embedding_settings.vector_dimensions,
        ),
        question_generation_prompt_version=WORKBENCH_RAG_EVAL_QUESTION_PROMPT_VERSION,
        question_generation_model=question_generator.generation_model,
    )


def make_apply_workbench_rag_eval_promotion(
    *,
    pool: object,
) -> ApplyWorkbenchRagEvalPromotion:
    embedding_settings = load_embedding_runtime_settings()
    return ApplyWorkbenchRagEvalPromotion(
        rag_eval_repository=PostgresWorkbenchRagEvalRepository(pool),
        embedding_generation_port=make_embedding_generation_port(embedding_settings),
        embedding_model_id=embedding_settings.local_model,
        embedding_dimensions=embedding_settings.vector_dimensions,
        embedding_text_builder=PromotedQuestionRuntimeEmbeddingTextBuilder(),
    )
