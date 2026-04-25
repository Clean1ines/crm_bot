import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY, call
from uuid import uuid4, UUID
import asyncpg

from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository


@pytest.fixture
def mock_pool():
    pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_conn
    mock_cm.__aexit__.return_value = None
    pool.acquire = MagicMock(return_value=mock_cm)
    pool.mock_conn = mock_conn
    return pool


@pytest.fixture
def knowledge_repo(mock_pool):
    return KnowledgeRepository(mock_pool)


class TestKnowledgeRepository:
    def test_init(self, knowledge_repo, mock_pool):
        assert knowledge_repo.pool is mock_pool

    # --------------------------------------------------------------------------
    # search
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    @patch("src.infrastructure.db.repositories.knowledge_repository.embed_text")
    async def test_search_success_hybrid_true(self, mock_embed_text, knowledge_repo, mock_pool):
        project_id = str(uuid4())
        query = "test query"
        limit = 10
        mock_embed_text.return_value = [0.1, 0.2, 0.3]  # dummy embedding

        # Mock vector results
        vector_rows = [
            {"id": uuid4(), "content": "vector chunk 1", "score": 0.9},
            {"id": uuid4(), "content": "vector chunk 2", "score": 0.8},
        ]
        # Mock FTS results
        fts_rows = [
            {"id": vector_rows[0]["id"], "content": "vector chunk 1", "score": 0.85},
            {"id": uuid4(), "content": "fts only chunk", "score": 0.7},
        ]

        mock_pool.mock_conn.fetch = AsyncMock(side_effect=[vector_rows, fts_rows])

        result = await knowledge_repo.search(project_id, query, limit, hybrid_fallback=True)

        # Embedding call
        mock_embed_text.assert_awaited_once_with(query)

        # acquire called twice
        assert mock_pool.acquire.call_count == 2

        # First fetch (vector)
        vector_sql = """
                SELECT id, content, (1 - (embedding <=> $1)) AS score
                FROM knowledge_base
                WHERE project_id = $2
                ORDER BY embedding <=> $1
                LIMIT $3
                """
        mock_pool.mock_conn.fetch.assert_any_call(vector_sql, ANY, UUID(project_id), limit * 2)

        # Second fetch (FTS)
        fts_sql = """
                SELECT id, content,
                       ts_rank_cd(tsv, plainto_tsquery('russian', $1)) AS score
                FROM knowledge_base
                WHERE project_id = $2
                  AND tsv @@ plainto_tsquery('russian', $1)
                ORDER BY score DESC
                LIMIT $3
                """
        mock_pool.mock_conn.fetch.assert_any_call(fts_sql, query, UUID(project_id), limit * 2)

        # Expected result: merged and sorted
        # The result should have 3 items (two from vector + one FTS-only)
        assert len(result) == 3
        # Check that the result contains expected fields
        for item in result:
            assert "id" in item
            assert "content" in item
            assert "score" in item
            assert "method" in item

    @pytest.mark.asyncio
    @patch("src.infrastructure.db.repositories.knowledge_repository.embed_text")
    async def test_search_success_hybrid_false(self, mock_embed_text, knowledge_repo, mock_pool):
        project_id = str(uuid4())
        query = "test"
        limit = 5
        mock_embed_text.return_value = [0.1, 0.2, 0.3]
        vector_rows = [
            {"id": uuid4(), "content": "c1", "score": 0.9},
            {"id": uuid4(), "content": "c2", "score": 0.8},
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=vector_rows)

        result = await knowledge_repo.search(project_id, query, limit, hybrid_fallback=False)

        assert mock_pool.acquire.call_count == 1
        mock_embed_text.assert_awaited_once_with(query)
        # Only vector query executed
        mock_pool.mock_conn.fetch.assert_called_once()
        # Result limited to limit (2 < limit)
        assert len(result) == len(vector_rows)
        for item in result:
            assert item["method"] == "vector"

    @pytest.mark.asyncio
    @patch("src.infrastructure.db.repositories.knowledge_repository.embed_text")
    async def test_search_limit_zero(self, mock_embed_text, knowledge_repo, mock_pool):
        mock_embed_text.return_value = [0.1]
        mock_pool.mock_conn.fetch = AsyncMock(side_effect=asyncpg.exceptions.InvalidParameterValueError("LIMIT 0"))
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError):
            await knowledge_repo.search(str(uuid4()), "q", limit=0)

    @pytest.mark.asyncio
    @patch("src.infrastructure.db.repositories.knowledge_repository.embed_text")
    async def test_search_empty_vector_results(self, mock_embed_text, knowledge_repo, mock_pool):
        mock_embed_text.return_value = [0.1]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=[])
        result = await knowledge_repo.search(str(uuid4()), "q")
        assert result == []

    @pytest.mark.asyncio
    @patch("src.infrastructure.db.repositories.knowledge_repository.embed_text")
    async def test_search_embed_text_error(self, mock_embed_text, knowledge_repo, mock_pool):
        mock_embed_text.side_effect = TypeError("embed failed")
        with pytest.raises(TypeError):
            await knowledge_repo.search(str(uuid4()), "q")

    # --------------------------------------------------------------------------
    # add_knowledge_batch
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    @patch("src.infrastructure.db.repositories.knowledge_repository.embed_batch")
    async def test_add_knowledge_batch_success(self, mock_embed_batch, knowledge_repo, mock_pool):
        project_id = str(uuid4())
        chunks = [{"content": "chunk1"}, {"content": "chunk2"}]
        document_id = str(uuid4())
        embeddings = [[0.1, 0.2], [0.3, 0.4]]
        mock_embed_batch.return_value = embeddings

        # Mock transaction
        mock_transaction = AsyncMock()
        mock_transaction.__aenter__.return_value = mock_pool.mock_conn
        mock_transaction.__aexit__.return_value = None
        mock_pool.mock_conn.transaction = MagicMock(return_value=mock_transaction)

        mock_pool.mock_conn.execute = AsyncMock()

        result = await knowledge_repo.add_knowledge_batch(project_id, chunks, document_id)

        assert mock_pool.acquire.call_count == 1
        mock_embed_batch.assert_awaited_once_with(["chunk1", "chunk2"])
        mock_pool.mock_conn.transaction.assert_called_once()

        expected_sql = """
                        INSERT INTO knowledge_base (project_id, document_id, content, embedding)
                        VALUES ($1, $2, $3, $4::vector)
                        """
        assert mock_pool.mock_conn.execute.call_count == len(chunks)
        # Check first call parameters
        mock_pool.mock_conn.execute.assert_any_call(
            expected_sql, UUID(project_id), UUID(document_id), "chunk1", ANY
        )
        mock_pool.mock_conn.execute.assert_any_call(
            expected_sql, UUID(project_id), UUID(document_id), "chunk2", ANY
        )
        assert result == len(chunks)

    @pytest.mark.asyncio
    async def test_add_knowledge_batch_empty_chunks(self, knowledge_repo):
        result = await knowledge_repo.add_knowledge_batch(str(uuid4()), [])
        assert result == 0

    @pytest.mark.asyncio
    @patch("src.infrastructure.db.repositories.knowledge_repository.embed_batch")
    async def test_add_knowledge_batch_embed_batch_error(self, mock_embed_batch, knowledge_repo):
        mock_embed_batch.side_effect = ValueError("embed batch failed")
        with pytest.raises(ValueError):
            await knowledge_repo.add_knowledge_batch(str(uuid4()), [{"content": "x"}])

    @pytest.mark.asyncio
    @patch("src.infrastructure.db.repositories.knowledge_repository.embed_batch")
    async def test_add_knowledge_batch_foreign_key_error(self, mock_embed_batch, knowledge_repo, mock_pool):
        mock_embed_batch.return_value = [[0.1]]
        mock_transaction = AsyncMock()
        mock_transaction.__aenter__.return_value = mock_pool.mock_conn
        mock_transaction.__aexit__.return_value = None
        mock_pool.mock_conn.transaction = MagicMock(return_value=mock_transaction)
        mock_pool.mock_conn.execute = AsyncMock(side_effect=asyncpg.exceptions.ForeignKeyViolationError("fk"))
        with pytest.raises(asyncpg.exceptions.ForeignKeyViolationError):
            await knowledge_repo.add_knowledge_batch(str(uuid4()), [{"content": "x"}])

    @pytest.mark.asyncio
    @patch("src.infrastructure.db.repositories.knowledge_repository.embed_batch")
    async def test_add_knowledge_batch_not_null_error(self, mock_embed_batch, knowledge_repo, mock_pool):
        mock_embed_batch.return_value = [[0.1]]
        mock_transaction = AsyncMock()
        mock_transaction.__aenter__.return_value = mock_pool.mock_conn
        mock_transaction.__aexit__.return_value = None
        mock_pool.mock_conn.transaction = MagicMock(return_value=mock_transaction)
        mock_pool.mock_conn.execute = AsyncMock(side_effect=asyncpg.exceptions.NotNullViolationError("null"))
        with pytest.raises(asyncpg.exceptions.NotNullViolationError):
            await knowledge_repo.add_knowledge_batch(str(uuid4()), [{"content": "x"}])

    # --------------------------------------------------------------------------
    # create_document
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_create_document_success(self, knowledge_repo, mock_pool):
        project_id = str(uuid4())
        file_name = "doc.pdf"
        file_size = 1024
        uploaded_by = "admin"
        expected_id = uuid4()
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value={"id": expected_id})

        result = await knowledge_repo.create_document(project_id, file_name, file_size, uploaded_by)

        expected_sql = """
                INSERT INTO knowledge_documents (project_id, file_name, file_size, uploaded_by)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(
            expected_sql, UUID(project_id), file_name, file_size, uploaded_by
        )
        assert result == str(expected_id)

    @pytest.mark.asyncio
    async def test_create_document_project_id_none_raises_type_error(self, knowledge_repo):
        with pytest.raises(TypeError):
            await knowledge_repo.create_document(None, "doc.pdf")

    @pytest.mark.asyncio
    async def test_create_document_file_name_none_raises_not_null(self, knowledge_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.fetchrow = AsyncMock(side_effect=asyncpg.exceptions.NotNullViolationError("null"))
        with pytest.raises(asyncpg.exceptions.NotNullViolationError):
            await knowledge_repo.create_document(project_id, None)

    @pytest.mark.asyncio
    async def test_create_document_foreign_key_error(self, knowledge_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(side_effect=asyncpg.exceptions.ForeignKeyViolationError("fk"))
        with pytest.raises(asyncpg.exceptions.ForeignKeyViolationError):
            await knowledge_repo.create_document(str(uuid4()), "doc.pdf")

    # --------------------------------------------------------------------------
    # get_documents
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_documents_success(self, knowledge_repo, mock_pool):
        project_id = str(uuid4())
        limit = 20
        offset = 0
        rows = [
            {"id": uuid4(), "file_name": "a.pdf", "file_size": 100, "status": "pending",
             "error": None, "uploaded_by": "admin", "created_at": "2021-01-01", "updated_at": "2021-01-01"},
            {"id": uuid4(), "file_name": "b.pdf", "file_size": 200, "status": "completed",
             "error": None, "uploaded_by": "admin", "created_at": "2021-01-02", "updated_at": "2021-01-02"},
        ]
        # Mock fetch for documents
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)
        # Mock fetchval for chunk counts (one per document)
        mock_pool.mock_conn.fetchval = AsyncMock(side_effect=[5, 10])

        result = await knowledge_repo.get_documents(project_id, limit, offset)

        expected_sql = """
                SELECT id, file_name, file_size, status, error, uploaded_by, created_at, updated_at
                FROM knowledge_documents
                WHERE project_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
            """
        mock_pool.mock_conn.fetch.assert_awaited_once_with(expected_sql, UUID(project_id), limit, offset)
        assert len(result) == len(rows)
        for i, doc in enumerate(result):
            assert doc["chunk_count"] == (5 if i == 0 else 10)
            assert "id" in doc
            assert "file_name" in doc

    @pytest.mark.asyncio
    async def test_get_documents_limit_zero(self, knowledge_repo, mock_pool):
        mock_pool.mock_conn.fetch = AsyncMock(side_effect=asyncpg.exceptions.InvalidParameterValueError("LIMIT 0"))
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError):
            await knowledge_repo.get_documents(str(uuid4()), limit=0)

    @pytest.mark.asyncio
    async def test_get_documents_empty(self, knowledge_repo, mock_pool):
        mock_pool.mock_conn.fetch = AsyncMock(return_value=[])
        result = await knowledge_repo.get_documents(str(uuid4()))
        assert result == []

    # --------------------------------------------------------------------------
    # get_document
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_document_success(self, knowledge_repo, mock_pool):
        doc_id = str(uuid4())
        row = {
            "id": doc_id,
            "project_id": str(uuid4()),
            "file_name": "doc.pdf",
            "file_size": 100,
            "status": "completed",
            "error": None,
            "uploaded_by": "admin",
            "created_at": "2021-01-01",
            "updated_at": "2021-01-01",
        }
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=42)

        result = await knowledge_repo.get_document(doc_id)

        expected_sql = """
                SELECT id, project_id, file_name, file_size, status, error, uploaded_by, created_at, updated_at
                FROM knowledge_documents
                WHERE id = $1
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(expected_sql, UUID(doc_id))
        assert result is not None
        assert result["id"] == doc_id
        assert result["chunk_count"] == 42

    @pytest.mark.asyncio
    async def test_get_document_not_found(self, knowledge_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)
        result = await knowledge_repo.get_document(str(uuid4()))
        assert result is None

    # --------------------------------------------------------------------------
    # update_document_status
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_update_document_status_success(self, knowledge_repo, mock_pool):
        doc_id = str(uuid4())
        status = "processing"
        error = None
        mock_pool.mock_conn.execute = AsyncMock()

        await knowledge_repo.update_document_status(doc_id, status, error)

        expected_sql = """
                UPDATE knowledge_documents
                SET status = $1, error = $2, updated_at = NOW()
                WHERE id = $3
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(expected_sql, status, error, UUID(doc_id))

    @pytest.mark.asyncio
    async def test_update_document_status_with_error(self, knowledge_repo, mock_pool):
        doc_id = str(uuid4())
        status = "failed"
        error = "some error"
        mock_pool.mock_conn.execute = AsyncMock()

        await knowledge_repo.update_document_status(doc_id, status, error)

        expected_sql = """
                UPDATE knowledge_documents
                SET status = $1, error = $2, updated_at = NOW()
                WHERE id = $3
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(expected_sql, status, error, UUID(doc_id))

    @pytest.mark.asyncio
    async def test_update_document_status_error_db(self, knowledge_repo, mock_pool):
        mock_pool.mock_conn.execute = AsyncMock(side_effect=asyncpg.exceptions.ConnectionDoesNotExistError("conn"))
        with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
            await knowledge_repo.update_document_status(str(uuid4()), "failed")

    # --------------------------------------------------------------------------
    # delete_document
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_delete_document_success(self, knowledge_repo, mock_pool):
        doc_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()

        await knowledge_repo.delete_document(doc_id)

        assert mock_pool.mock_conn.execute.call_count == 2
        expected_sql1 = "DELETE FROM knowledge_base WHERE document_id = $1"
        expected_sql2 = "DELETE FROM knowledge_documents WHERE id = $1"
        calls = [call(expected_sql1, UUID(doc_id)), call(expected_sql2, UUID(doc_id))]
        mock_pool.mock_conn.execute.assert_has_calls(calls, any_order=False)

    @pytest.mark.asyncio
    async def test_delete_document_not_found(self, knowledge_repo, mock_pool):
        doc_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()  # no exception
        await knowledge_repo.delete_document(doc_id)
        # Should succeed even if no rows affected
        mock_pool.mock_conn.execute.assert_any_call("DELETE FROM knowledge_base WHERE document_id = $1", UUID(doc_id))
        mock_pool.mock_conn.execute.assert_any_call("DELETE FROM knowledge_documents WHERE id = $1", UUID(doc_id))
