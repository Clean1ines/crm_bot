# Lazy fastembed rewrite report\n\n## Goal\n\n- Fully rewrite `src/infrastructure/llm/embedding_service.py`.\n- Remove module-level `fastembed` import.\n- Preserve typed contracts without `Any`.\n- Verify plain FastAPI app import no longer pulls `fastembed`.\n\n## Before\n\n```python\n"""
Embedding generation service using fastembed.
"""

import asyncio
from fastembed import TextEmbedding

from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        logger.info("Loading embedding model 'BAAI/bge-small-en-v1.5'")
        _model = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _model


async def embed_text(text: str) -> list[float]:
    logger.debug(f"Generating embedding for text of length {len(text)}")
    loop = asyncio.get_event_loop()
    model = _get_model()
    embedding = await loop.run_in_executor(None, lambda: list(model.embed([text]))[0])
    return embedding.tolist()


async def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    logger.debug(f"Generating embeddings for batch of {len(texts)} texts")
    loop = asyncio.get_event_loop()
    model = _get_model()
    embeddings = await loop.run_in_executor(None, lambda: list(model.embed(texts)))
    return [emb.tolist() for emb in embeddings]
\n```\n\n## After\n\n```python\n"""
Embedding generation service using fastembed.

fastembed is intentionally imported lazily inside _create_model().
Plain application imports, webhook imports, and FastAPI app assembly must not
load ONNX / fastembed runtime dependencies until embeddings are actually needed.
"""

import asyncio
from collections.abc import Iterable
from typing import Protocol, cast

from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"


class EmbeddingVector(Protocol):
    def tolist(self) -> list[float]: ...


class EmbeddingModel(Protocol):
    def embed(self, documents: list[str]) -> Iterable[EmbeddingVector]: ...


_model: EmbeddingModel | None = None


def _create_model() -> EmbeddingModel:
    """
    Create the concrete fastembed model only when embeddings are requested.

    Importing TextEmbedding here keeps `import src.interfaces.http.app` free from
    fastembed and its heavy transitive dependencies.
    """
    from fastembed import TextEmbedding

    return cast(EmbeddingModel, TextEmbedding(EMBEDDING_MODEL_NAME))


def _get_model() -> EmbeddingModel:
    global _model

    if _model is None:
        logger.info("Loading embedding model '%s'", EMBEDDING_MODEL_NAME)
        _model = _create_model()

    return _model


def _embed_one_sync(model: EmbeddingModel, text: str) -> list[float]:
    vectors = list(model.embed([text]))
    if not vectors:
        return []

    return vectors[0].tolist()


def _embed_batch_sync(model: EmbeddingModel, texts: list[str]) -> list[list[float]]:
    return [vector.tolist() for vector in model.embed(texts)]


async def embed_text(text: str) -> list[float]:
    logger.debug("Generating embedding for text of length %s", len(text))

    loop = asyncio.get_running_loop()
    model = _get_model()

    return await loop.run_in_executor(None, _embed_one_sync, model, text)


async def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    logger.debug("Generating embeddings for batch of %s texts", len(texts))

    loop = asyncio.get_running_loop()
    model = _get_model()

    return await loop.run_in_executor(None, _embed_batch_sync, model, texts)
\n```\n\n## git diff -- src/infrastructure/llm/embedding_service.py\n\nexit_code: `0`\n\n```text\ndiff --git a/src/infrastructure/llm/embedding_service.py b/src/infrastructure/llm/embedding_service.py
index 95820fe..60305a2 100644
--- a/src/infrastructure/llm/embedding_service.py
+++ b/src/infrastructure/llm/embedding_service.py
@@ -1,38 +1,83 @@
 """
 Embedding generation service using fastembed.
+
+fastembed is intentionally imported lazily inside _create_model().
+Plain application imports, webhook imports, and FastAPI app assembly must not
+load ONNX / fastembed runtime dependencies until embeddings are actually needed.
 """
 
 import asyncio
-from fastembed import TextEmbedding
+from collections.abc import Iterable
+from typing import Protocol, cast
 
 from src.infrastructure.logging.logger import get_logger
 
 logger = get_logger(__name__)
 
-_model = None
+EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
+
+
+class EmbeddingVector(Protocol):
+    def tolist(self) -> list[float]: ...
+
+
+class EmbeddingModel(Protocol):
+    def embed(self, documents: list[str]) -> Iterable[EmbeddingVector]: ...
+
 
+_model: EmbeddingModel | None = None
 
-def _get_model():
+
+def _create_model() -> EmbeddingModel:
+    """
+    Create the concrete fastembed model only when embeddings are requested.
+
+    Importing TextEmbedding here keeps `import src.interfaces.http.app` free from
+    fastembed and its heavy transitive dependencies.
+    """
+    from fastembed import TextEmbedding
+
+    return cast(EmbeddingModel, TextEmbedding(EMBEDDING_MODEL_NAME))
+
+
+def _get_model() -> EmbeddingModel:
     global _model
+
     if _model is None:
-        logger.info("Loading embedding model 'BAAI/bge-small-en-v1.5'")
-        _model = TextEmbedding("BAAI/bge-small-en-v1.5")
+        logger.info("Loading embedding model '%s'", EMBEDDING_MODEL_NAME)
+        _model = _create_model()
+
     return _model
 
 
+def _embed_one_sync(model: EmbeddingModel, text: str) -> list[float]:
+    vectors = list(model.embed([text]))
+    if not vectors:
+        return []
+
+    return vectors[0].tolist()
+
+
+def _embed_batch_sync(model: EmbeddingModel, texts: list[str]) -> list[list[float]]:
+    return [vector.tolist() for vector in model.embed(texts)]
+
+
 async def embed_text(text: str) -> list[float]:
-    logger.debug(f"Generating embedding for text of length {len(text)}")
-    loop = asyncio.get_event_loop()
+    logger.debug("Generating embedding for text of length %s", len(text))
+
+    loop = asyncio.get_running_loop()
     model = _get_model()
-    embedding = await loop.run_in_executor(None, lambda: list(model.embed([text]))[0])
-    return embedding.tolist()
+
+    return await loop.run_in_executor(None, _embed_one_sync, model, text)
 
 
 async def embed_batch(texts: list[str]) -> list[list[float]]:
     if not texts:
         return []
-    logger.debug(f"Generating embeddings for batch of {len(texts)} texts")
-    loop = asyncio.get_event_loop()
+
+    logger.debug("Generating embeddings for batch of %s texts", len(texts))
+
+    loop = asyncio.get_running_loop()
     model = _get_model()
-    embeddings = await loop.run_in_executor(None, lambda: list(model.embed(texts)))
-    return [emb.tolist() for emb in embeddings]
+
+    return await loop.run_in_executor(None, _embed_batch_sync, model, texts)\n```\n\n## python -m py_compile src/infrastructure/llm/embedding_service.py\n\nexit_code: `0`\n\n```text\n\n```\n\n## ruff format src/infrastructure/llm/embedding_service.py\n\nexit_code: `0`\n\n```text\n1 file left unchanged\n```\n\n## ruff check src/infrastructure/llm/embedding_service.py\n\nexit_code: `0`\n\n```text\nAll checks passed!\n```\n\n## mypy src/infrastructure/llm/embedding_service.py\n\nexit_code: `0`\n\n```text\nSuccess: no issues found in 1 source file\n```\n\n## pytest -q tests/infrastructure/llm/test_rag_pipeline_contract.py tests/api/test_webhooks.py\n\nexit_code: `0`\n\n```text\n============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/haku/crm_bot
configfile: pytest.ini
plugins: anyio-4.12.1, langsmith-0.7.37, cov-7.1.0, asyncio-1.3.0, env-1.6.0, timeout-2.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 21 items

tests/infrastructure/llm/test_rag_pipeline_contract.py .....             [ 23%]
tests/api/test_webhooks.py ................                              [100%]

=============================== warnings summary ===============================
src/infrastructure/config/settings.py:10
  /home/haku/crm_bot/src/infrastructure/config/settings.py:10: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
================================ tests coverage ================================
_______________ coverage: platform linux, python 3.12.3-final-0 ________________

Name                                                                  Stmts   Miss  Cover   Missing
---------------------------------------------------------------------------------------------------
src/__init__.py                                                           0      0   100%
src/application/dto/__init__.py                                           8      0   100%
src/application/dto/auth_dto.py                                          94     30    68%   13, 17, 21-26, 30-32, 45, 55, 64-65, 77, 91, 99-106, 125, 133-134, 157, 167, 181, 192, 202-203
src/application/dto/control_plane_dto.py                                 73     26    64%   8, 12-18, 22-27, 44, 58, 71-72, 93, 99, 108-109, 124, 127, 139, 142
src/application/dto/knowledge_dto.py                                     10      2    80%   11, 14
src/application/dto/project_dto.py                                      177     79    55%   21-23, 27-29, 33-47, 51-55, 63-68, 76-80, 92-95, 106, 114-117, 129-131, 140, 148-151, 163-167, 176, 184-187, 201-205, 220, 230, 245, 269, 284, 307-310, 326, 337-338, 355, 371, 378
src/application/dto/runtime_dto.py                                       58     20    66%   14-16, 20-22, 30-32, 49-50, 59, 77, 102-108
src/application/dto/webhook_dto.py                                        6      0   100%
src/application/errors.py                                                17      0   100%
src/application/orchestration/__init__.py                                 2      0   100%
src/application/orchestration/client_message_service.py                 133     99    26%   28-29, 47-56, 59-61, 72-97, 100, 118, 127, 132-136, 147-171, 176-182, 187-197, 209-224, 236-259, 269-284, 294-298, 318-319, 340-354, 366-378, 390-409, 421-424, 435-443
src/application/orchestration/conversation_orchestrator.py               81     46    43%   28-29, 38-54, 87-145, 154, 157, 160, 163, 167, 172, 175, 178, 181, 186, 189, 200, 214, 225, 238
src/application/orchestration/graph_factory.py                           57     36    37%   46-47, 68-87, 90-92, 99, 103, 108-110, 123, 139, 184-199, 207-214
src/application/orchestration/manager_reply_service.py                  105     81    23%   23-27, 34, 45, 58-101, 110, 122-132, 139-149, 156-169, 174-179, 182-188, 193-195, 206-216, 226-234, 244-249, 259-270, 273-276, 279-281, 286-293, 304
src/application/orchestration/project_runtime_loader.py                  13      8    38%   14-15, 20-31
src/application/orchestration/transport_sender_port.py                    2      0   100%
src/application/ports/agent_runtime_port.py                              16      0   100%
src/application/ports/cache_port.py                                      28     10    64%   42, 45, 48, 51, 54, 57, 60, 63, 66, 69
src/application/ports/client_port.py                                      3      0   100%
src/application/ports/event_port.py                                       4      0   100%
src/application/ports/google_identity_port.py                             9      0   100%
src/application/ports/knowledge_port.py                                  15      0   100%
src/application/ports/lock_port.py                                        7      2    71%   11, 14
src/application/ports/logger_port.py                                     13      5    62%   14, 17, 20, 23, 26
src/application/ports/manager_bot_port.py                                10      0   100%
src/application/ports/memory_port.py                                      5      0   100%
src/application/ports/project_port.py                                    14      0   100%
src/application/ports/telegram_port.py                                    6      0   100%
src/application/ports/thread_port.py                                      9      0   100%
src/application/ports/user_port.py                                        5      0   100%
src/application/services/auth_service.py                                218    162    26%   51-53, 64-66, 69-76, 80, 84, 88, 91-99, 104-105, 113, 118, 121, 124, 127, 130-133, 136-141, 146-157, 162-172, 177-187, 190-209, 218-232, 237-244, 251-258, 268-292, 299-305, 308-311, 316-320, 325-330, 335-342, 349-351, 361-377, 380-400, 411-424, 431-452
src/application/services/client_query_service.py                         62     48    23%   12-18, 22-32, 43-46, 57-67, 72-104, 113-116
src/application/services/knowledge_service.py                           109     84    23%   35-39, 42-46, 49-50, 53-59, 62-70, 73-74, 87-120, 125-129, 139-146, 159-178, 182-188, 192-199, 203-209, 213-219, 223-224, 228-232
src/application/services/manager_bot_service.py                          86     71    17%   25-30, 33-39, 45-52, 62-126, 136-220, 229-289
src/application/services/platform_bot_service.py                         30     17    43%   27-35, 40-43, 48-52, 59-64, 67-73
src/application/services/project_command_service.py                     136    104    24%   30-32, 36-38, 42-45, 48-49, 52-56, 61-67, 70-74, 79-92, 97-110, 113-125, 128-140, 143-159, 164-167, 172-197, 202-208, 213-216, 221-228, 233-240, 245-252, 257-271, 276-293
src/application/services/project_query_service.py                        64     39    39%   25-27, 31-37, 42, 45, 50, 55, 58-59, 65-72, 75-78, 85-89, 94-98, 105-109, 119-123, 136-147
src/application/services/project_runtime_guards.py                       62     49    21%   29-30, 33-35, 40-60, 68-102, 105-113
src/application/services/project_service.py                              15      8    47%   12, 20-30
src/application/services/thread_command_service.py                       15      7    53%   12-13, 16-17, 26-32, 41
src/application/services/thread_query_service.py                         70     45    36%   15, 34-39, 50-55, 64, 67, 75-86, 95-96, 105-106, 115-118, 121-122, 127-132, 137-142, 145, 154-155, 160-169, 172-173, 176
src/application/services/webhook_dispatcher.py                           65      9    86%   26, 33, 39, 42, 55, 74, 93, 101-104
src/domain/__init__.py                                                    0      0   100%
src/domain/control_plane/__init__.py                                      0      0   100%
src/domain/control_plane/memberships.py                                   8      5    38%   8-11, 16
src/domain/control_plane/project_configuration.py                       110     50    55%   23, 37-47, 63, 77-87, 102-107, 118-127, 142, 165, 176, 191-199, 207-213, 217, 221-237, 241-244
src/domain/control_plane/project_views.py                               124     40    68%   8, 12, 16-32, 36-40, 57, 72, 98, 112, 139, 148-150, 164, 191, 203-213, 229, 241-251, 262
src/domain/control_plane/roles.py                                        13      0   100%
src/domain/identity/__init__.py                                           0      0   100%
src/domain/identity/auth_providers.py                                    10      0   100%
src/domain/identity/user_views.py                                        70     21    70%   6, 10-15, 29-31, 41, 60-67, 78-85, 94, 103, 112, 120
src/domain/project_plane/__init__.py                                      0      0   100%
src/domain/project_plane/client_views.py                                 49      8    84%   7-9, 30-31, 57, 82-83
src/domain/project_plane/event_views.py                                  40     24    40%   9-23, 27-29, 42-43, 52-60
src/domain/project_plane/json_types.py                                   23     16    30%   11-20, 24-34
src/domain/project_plane/knowledge_views.py                              31      0   100%
src/domain/project_plane/manager_assignments.py                          53     29    45%   37, 41-43, 46-50, 60, 76-99, 117-125
src/domain/project_plane/manager_notifications.py                        19     11    42%   34-57
src/domain/project_plane/manager_reply_history.py                        38     21    45%   10-24, 39-44, 55
src/domain/project_plane/memory_views.py                                 20      5    75%   8-10, 24, 34
src/domain/project_plane/queue_views.py                                  45     28    38%   8-22, 26-28, 32-34, 48, 58-72
src/domain/project_plane/thread_runtime.py                               49     23    53%   10, 14-20, 38-40, 61-62, 70-79
src/domain/project_plane/thread_status.py                                 6      0   100%
src/domain/project_plane/thread_views.py                                133     44    67%   8-22, 26, 30-32, 36-38, 60-62, 90, 117-119, 127, 143-144, 151, 166, 180, 198, 221, 237, 243, 249-251, 263, 271
src/domain/runtime/__init__.py                                            0      0   100%
src/domain/runtime/delivery.py                                           31     31     0%   1-56
src/domain/runtime/dialog_state.py                                       47     25    47%   26, 37-40, 48-61, 69, 77-87
src/domain/runtime/escalation.py                                         28     28     0%   1-57
src/domain/runtime/graph_contract.py                                    103    103     0%   13-314
src/domain/runtime/intent_extraction.py                                  48     48     0%   1-89
src/domain/runtime/knowledge_search.py                                   45     45     0%   1-81
src/domain/runtime/load_state.py                                         74     74     0%   1-117
src/domain/runtime/persistence.py                                        64     64     0%   1-166
src/domain/runtime/policy/__init__.py                                     3      3     0%   1-4
src/domain/runtime/policy/decision_engine.py                             79     79     0%   1-159
src/domain/runtime/policy/intent_topic.py                                49     49     0%   1-109
src/domain/runtime/policy/lifecycle.py                                    9      9     0%   1-19
src/domain/runtime/policy/repeat_detection.py                            74     74     0%   1-165
src/domain/runtime/policy/result.py                                      37     37     0%   1-77
src/domain/runtime/policy/transitions.py                                  5      5     0%   1-70
src/domain/runtime/policy_decision.py                                     2      2     0%   1-3
src/domain/runtime/project_runtime_profile.py                            36     16    56%   12-13, 30-36, 56-59, 63-66, 70-74
src/domain/runtime/prompting.py                                          51     51     0%   1-143
src/domain/runtime/response_generation.py                                35     35     0%   1-85
src/domain/runtime/state_contracts.py                                   116      0   100%
src/domain/runtime/tool_execution.py                                     25     25     0%   1-49
src/domain/runtime/value_parsing.py                                      38     35     8%   2-18, 22-36, 40-42
src/infrastructure/__init__.py                                            0      0   100%
src/infrastructure/app/__init__.py                                        0      0   100%
src/infrastructure/app/resources.py                                      33     26    21%   20-42, 46-51, 55-62, 71-105
src/infrastructure/config/__init__.py                                     0      0   100%
src/infrastructure/config/settings.py                                    65      8    88%   129-130, 140-146, 152
src/infrastructure/db/__init__.py                                         0      0   100%
src/infrastructure/db/repositories/__init__.py                           10      0   100%
src/infrastructure/db/repositories/client_repository.py                  78     57    27%   18-24, 28, 32-46, 50-52, 56-58, 64-74, 78-81, 87, 120, 139, 158, 177-178, 188, 198-212, 220-235
src/infrastructure/db/repositories/event_repository.py                   48     32    33%   21-22, 31-58, 66-116, 124-163, 171-206, 214, 223-269
src/infrastructure/db/repositories/knowledge_repository.py               92     75    18%   29-35, 40, 43-47, 56-138, 146-171, 180-200, 208-253, 258-278, 299-305, 317-329
src/infrastructure/db/repositories/memory_repository.py                  73     58    21%   21-23, 41-42, 64-91, 114-134, 158-181, 193-205, 223-260, 274-277, 304-319
src/infrastructure/db/repositories/metrics_repository.py                 71     60    15%   31-32, 54-103, 125-174, 187-244
src/infrastructure/db/repositories/project/__init__.py                   10      0   100%
src/infrastructure/db/repositories/project/base.py                       49     29    41%   22-24, 33, 36, 39, 42-59, 62-72
src/infrastructure/db/repositories/project/project_channels.py            8      3    62%   21-42
src/infrastructure/db/repositories/project/project_commands.py           29     21    28%   10-15, 26-31, 34-39, 42-68, 71-75, 85-86
src/infrastructure/db/repositories/project/project_configuration.py      22     15    32%   14-77, 102-103, 132-133, 160-161
src/infrastructure/db/repositories/project/project_integrations.py        7      3    57%   19-41
src/infrastructure/db/repositories/project/project_members.py            59     45    24%   18-20, 26-53, 60-106, 118-119, 137-159, 162-174, 179-238, 243-244, 259-260, 272-283
src/infrastructure/db/repositories/project/project_queries.py            73     63    14%   17-66, 71-85, 90-108, 111-130, 135-162, 167-178, 186-196
src/infrastructure/db/repositories/project/project_tokens.py             48     36    25%   10-18, 21-26, 38-46, 51-56, 68-69, 77-78, 88-89, 99-100, 110-117, 120-128
src/infrastructure/db/repositories/queue_repository.py                   77     62    19%   25-26, 34-58, 61-114, 119-125, 142-168, 173-222, 225-254, 257-267
src/infrastructure/db/repositories/thread/__init__.py                     5      0   100%
src/infrastructure/db/repositories/thread/lifecycle.py                   56     41    27%   11, 21-53, 56-74, 77-91, 94-98, 109, 112-115, 133-147, 164-167
src/infrastructure/db/repositories/thread/messages.py                    39     29    26%   13, 16-38, 41-54, 67-82, 90-124
src/infrastructure/db/repositories/thread/read.py                        57     47    18%   18, 23-53, 64-161, 164-176
src/infrastructure/db/repositories/thread/runtime_state.py               67     52    22%   17, 20-33, 36-53, 56-69, 79-116, 128-145, 148-163
src/infrastructure/db/repositories/user_repository.py                   253    213    16%   42-57, 69-71, 79-91, 112-113, 133-210, 218-259, 273-285, 296, 308-341, 349-362, 376-390, 402-406, 412-417, 429-443, 449-500, 511-520, 526-537, 543-545, 561-576, 582-593, 599-609, 618-661, 674-691, 702-728, 738-761, 769-778, 796-819, 827-850
src/infrastructure/identity/google_verifier.py                           29     22    24%   13-14, 17-45
src/infrastructure/llm/__init__.py                                        0      0   100%
src/infrastructure/llm/chunker.py                                       128    103    20%   19-20, 23-36, 42-53, 64-75, 78-81, 87, 90-96, 102-142, 145, 148-164, 169-172, 175-184, 187-188, 191-198, 201-204, 207-216, 219-223, 227, 231
src/infrastructure/llm/embedding_service.py                              36     21    42%   38-40, 46-50, 54-58, 62, 66-71, 75-83
src/infrastructure/llm/model_registry.py                                 76     58    24%   17-20, 24-38, 42-45, 49, 59-60, 64-89, 93-121, 125, 129, 139-142, 148-149
src/infrastructure/llm/model_selector.py                                 34     34     0%   5-69
src/infrastructure/llm/query_expander.py                                 34     20    41%   30, 45-46, 49-83, 87-98
src/infrastructure/llm/rag_contract.py                                   56      9    84%   93, 103, 108, 111-112, 119-122
src/infrastructure/llm/rag_service.py                                   108     11    90%   64, 72-73, 76, 81, 121, 137, 154, 175, 193, 246
src/infrastructure/llm/rate_limit_tracker.py                             52     39    25%   24, 27-29, 38-72, 81-90, 102-105, 109-113
src/infrastructure/logging/__init__.py                                    0      0   100%
src/infrastructure/logging/logger.py                                     50     21    58%   88-116
src/infrastructure/queue/__init__.py                                      0      0   100%
src/infrastructure/queue/handlers/__init__.py                             0      0   100%
src/infrastructure/queue/handlers/metrics.py                             41     41     0%   3-90
src/infrastructure/queue/handlers/notify_manager.py                     114    114     0%   3-330
src/infrastructure/queue/job_dispatcher.py                               31     31     0%   3-67
src/infrastructure/queue/job_exceptions.py                                3      3     0%   4-12
src/infrastructure/queue/job_types.py                                     4      4     0%   3-7
src/infrastructure/queue/retry_policy.py                                 39     39     0%   3-61
src/infrastructure/queue/runtime.py                                      61     61     0%   3-121
src/infrastructure/queue/stale_recovery.py                               16     16     0%   3-36
src/infrastructure/queue/telegram_sender.py                              31     31     0%   3-68
src/infrastructure/queue/worker.py                                        5      5     0%   3-11
src/infrastructure/queue/worker_loop.py                                  44     44     0%   3-98
src/infrastructure/redis/__init__.py                                      0      0   100%
src/infrastructure/redis/client.py                                       13      7    46%   19-28
src/infrastructure/redis/lock.py                                         19     19     0%   7-63
src/infrastructure/telegram/__init__.py                                   0      0   100%
src/interfaces/__init__.py                                                0      0   100%
src/interfaces/composition/__init__.py                                    0      0   100%
src/interfaces/composition/fastapi_lifespan.py                           73     46    37%   72-114, 123-134, 157-174
src/interfaces/composition/project_repositories.py                        7      1    86%   16
src/interfaces/http/__init__.py                                           0      0   100%
src/interfaces/http/app.py                                               54      0   100%
src/interfaces/http/auth.py                                             140     54    61%   19-26, 98-114, 122-147, 163-164, 174-175, 184-185, 195-196, 204-205, 213-214, 226-227, 236-237, 250-251, 261-262, 270-271, 280-281, 295-296, 304-305, 316-317
src/interfaces/http/bot.py                                               25     17    32%   13-42
src/interfaces/http/chat.py                                              29     10    66%   31-35, 45-60
src/interfaces/http/clients.py                                           15      5    67%   26, 45-51
src/interfaces/http/dependencies.py                                     130     69    47%   79, 86, 102-105, 118-121, 130, 136, 157, 170, 179, 188, 195, 208, 221, 234, 241, 248, 253, 260, 273, 283, 299, 316, 326-333, 343, 361-385, 398-405, 423-459
src/interfaces/http/knowledge.py                                         41     16    61%   46, 53, 57, 73-80, 96-113
src/interfaces/http/limits.py                                            15      6    60%   21-26
src/interfaces/http/logs.py                                              20     14    30%   18-37
src/interfaces/http/metrics.py                                           23     11    52%   38-56
src/interfaces/http/projects.py                                         172     28    84%   147, 157, 166, 176, 185, 195, 209, 222, 233, 244, 254, 266-267, 278, 291-292, 302, 316-319, 332, 346, 364, 382, 399, 414, 431, 446, 465
src/interfaces/http/threads.py                                           48     11    77%   57-65, 80, 94-102, 114, 126, 143-147, 162
src/interfaces/http/webhooks.py                                          57      0   100%
src/interfaces/telegram/__init__.py                                       0      0   100%
src/interfaces/telegram/client_bot.py                                    67     49    27%   25-26, 30-31, 35-37, 41-53, 57-63, 67-68, 79-80, 96-122, 137-164
src/interfaces/telegram/manager_bot.py                                   35     26    26%   27-80
src/interfaces/telegram/platform_admin/__init__.py                        0      0   100%
src/interfaces/telegram/platform_admin/handlers.py                      373    298    20%   46-48, 54-56, 60-63, 67-73, 77-79, 85-86, 90-101, 105, 109, 113-117, 127-144, 148, 160-161, 165-176, 180-192, 196-213, 217-245, 249-284, 288-323, 327, 334, 338-339, 346, 352, 358-361, 371-374, 384-387, 395-410, 416-426, 432-448, 452-468, 474, 482, 490-510, 514-515, 521-523, 543-558, 562-579, 583-606, 612-641, 645-662, 666-682, 686-702, 706-710, 719-727, 733-735, 741-749, 753-757
src/interfaces/telegram/platform_admin/keyboards.py                      44     33    25%   14-19, 30-31, 43-48, 54-103, 107-108, 114-115, 121-122
src/interfaces/telegram/platform_admin/knowledge_upload.py               62     51    18%   22-28, 32-39, 45-114
src/interfaces/telegram/platform_bot.py                                 103     76    26%   36-42, 46, 50-51, 57-68, 77-88, 96-101, 107-108, 116-120, 128-135, 141-158, 166-175, 185-207, 216-226, 236-255
src/tools/__init__.py                                                    19     12    37%   60-82, 96
src/tools/builtins.py                                                   187    137    27%   23-25, 29-43, 47-59, 127-128, 146-210, 277-280, 298-383, 445-446, 451-502, 557-558, 563-618, 651, 657, 712-713, 718-741, 786-787, 792-820
src/tools/http_tool.py                                                  132     98    26%   79-98, 105-119, 122-154, 159-167, 179-188, 200-208, 227-233, 236-251, 255-269, 273-281, 293-296, 300-304, 308-313, 317-327, 331, 338, 342-349
src/tools/registry.py                                                   129     83    36%   35-38, 57, 63-74, 80-86, 101-113, 123-124, 130-134, 145-173, 180-186, 195-206, 209-220, 229, 241-246, 249-261, 271-279, 290-298, 308-312, 324, 327-332, 335, 338
src/utils/encryption.py                                                  32     24    25%   18-27, 34-38, 46-54
src/utils/uuid_utils.py                                                   5      3    40%   14-16
---------------------------------------------------------------------------------------------------
TOTAL                                                                  8142   5156    37%
Coverage HTML written to dir htmlcov
======================== 21 passed, 1 warning in 6.99s =========================\n```\n\n## python -X importtime -c 'import src.interfaces.http.app' 2> reports/importtime-app-after-fastembed-lazy.txt\n\nexit_code: `0`\n\n```text\n2026-04-27 23:58:44 [debug    ] ToolRegistry initialized\n```\n\n## rg -n 'langchain_groq|PyPDF2|fastembed' reports/importtime-app-after-fastembed-lazy.txt || true\n\nexit_code: `0`\n\n```text\n\n```\n\n## rg -n 'from fastembed import|import fastembed|\bAny\b|from typing import .*Any' src/infrastructure/llm/embedding_service.py || true\n\nexit_code: `0`\n\n```text\n38:    from fastembed import TextEmbedding\n```\n