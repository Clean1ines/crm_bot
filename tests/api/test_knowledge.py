import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from uuid import uuid4
import io

from src.main import app
from src.api.dependencies import get_project_repo, get_pool


@pytest.fixture
def mock_project_repo():
    repo = AsyncMock()
    repo.project_exists = AsyncMock()
    return repo


@pytest.fixture
def mock_pool():
    pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__.return_value = mock_conn
    mock_cm.__aexit__.return_value = None
    pool.acquire = MagicMock(return_value=mock_cm)
    return pool


@pytest.fixture(autouse=True)
def override_dependencies(mock_project_repo, mock_pool):
    original_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_project_repo] = lambda: mock_project_repo
    app.dependency_overrides[get_pool] = lambda: mock_pool
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)


@pytest.fixture
def client():
    return TestClient(app)


class TestKnowledgeUpload:
    """Тесты для POST /api/projects/{project_id}/knowledge"""

    def test_upload_success_txt(self, client, mock_project_repo, mock_pool):
        """Успешная загрузка .txt файла"""
        project_id = str(uuid4())
        mock_project_repo.project_exists.return_value = True

        chunks = [
            {"content": "chunk 1", "metadata": {}},
            {"content": "chunk 2", "metadata": {}}
        ]
        embeddings = [[0.1, 0.2], [0.3, 0.4]]

        with patch("src.api.knowledge.ChunkerService") as MockChunker:
            mock_chunker = AsyncMock()
            MockChunker.return_value = mock_chunker
            mock_chunker.process_file = AsyncMock(return_value=chunks)

            with patch("src.api.knowledge.embed_text") as mock_embed:
                mock_embed.side_effect = embeddings

                with patch("src.api.knowledge.KnowledgeRepository") as MockRepo:
                    mock_repo = AsyncMock()
                    MockRepo.return_value = mock_repo
                    mock_repo.add_knowledge_batch = AsyncMock(return_value=2)

                    with patch("src.core.config.settings.ADMIN_API_TOKEN", "valid-token"):
                        files = {"file": ("test.txt", b"Test content", "text/plain")}
                        headers = {"Authorization": "Bearer valid-token"}

                        response = client.post(
                            f"/api/projects/{project_id}/knowledge",
                            files=files,
                            headers=headers
                        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Uploaded 2 chunks"
        assert data["chunks"] == 2

        mock_project_repo.project_exists.assert_awaited_once_with(project_id)
        mock_chunker.process_file.assert_awaited_once()
        assert mock_embed.call_count == 2
        mock_repo.add_knowledge_batch.assert_awaited_once_with(
            project_id, chunks, embeddings
        )

    def test_upload_success_pdf(self, client, mock_project_repo, mock_pool):
        """Успешная загрузка PDF файла"""
        project_id = str(uuid4())
        mock_project_repo.project_exists.return_value = True

        with patch("src.api.knowledge.ChunkerService") as MockChunker:
            mock_chunker = AsyncMock()
            MockChunker.return_value = mock_chunker
            mock_chunker.process_file = AsyncMock(return_value=[{"content": "pdf chunk"}])

            with patch("src.api.knowledge.embed_text") as mock_embed:
                mock_embed.return_value = [0.1, 0.2]

                with patch("src.api.knowledge.KnowledgeRepository") as MockRepo:
                    mock_repo = AsyncMock()
                    MockRepo.return_value = mock_repo
                    mock_repo.add_knowledge_batch = AsyncMock(return_value=1)

                    with patch("src.core.config.settings.ADMIN_API_TOKEN", "valid-token"):
                        files = {"file": ("test.pdf", b"%PDF-1.4...", "application/pdf")}
                        headers = {"Authorization": "Bearer valid-token"}

                        response = client.post(
                            f"/api/projects/{project_id}/knowledge",
                            files=files,
                            headers=headers
                        )

        assert response.status_code == 200
        data = response.json()
        assert data["chunks"] == 1

    def test_upload_empty_text(self, client, mock_project_repo, mock_pool):
        """Загрузка файла без текста"""
        project_id = str(uuid4())
        mock_project_repo.project_exists.return_value = True

        with patch("src.api.knowledge.ChunkerService") as MockChunker:
            mock_chunker = AsyncMock()
            MockChunker.return_value = mock_chunker
            mock_chunker.process_file = AsyncMock(return_value=[])

            with patch("src.core.config.settings.ADMIN_API_TOKEN", "valid-token"):
                files = {"file": ("empty.txt", b"", "text/plain")}
                headers = {"Authorization": "Bearer valid-token"}

                response = client.post(
                    f"/api/projects/{project_id}/knowledge",
                    files=files,
                    headers=headers
                )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "No text extracted"
        assert data["chunks"] == 0

    def test_upload_project_not_found(self, client, mock_project_repo):
        """Проект не найден"""
        project_id = str(uuid4())
        mock_project_repo.project_exists.return_value = False

        with patch("src.core.config.settings.ADMIN_API_TOKEN", "valid-token"):
            files = {"file": ("test.txt", b"test", "text/plain")}
            headers = {"Authorization": "Bearer valid-token"}

            response = client.post(
                f"/api/projects/{project_id}/knowledge",
                files=files,
                headers=headers
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Project not found"

    def test_upload_missing_file(self, client):
        """Файл не передан"""
        project_id = str(uuid4())
        with patch("src.core.config.settings.ADMIN_API_TOKEN", "valid-token"):
            headers = {"Authorization": "Bearer valid-token"}

            response = client.post(
                f"/api/projects/{project_id}/knowledge",
                headers=headers
            )

        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any(err["loc"] == ["body", "file"] for err in errors)

    def test_upload_unsupported_file_type(self, client, mock_project_repo):
        """Неподдерживаемый тип файла"""
        project_id = str(uuid4())
        mock_project_repo.project_exists.return_value = True

        with patch("src.api.knowledge.ChunkerService") as MockChunker:
            mock_chunker = AsyncMock()
            MockChunker.return_value = mock_chunker
            mock_chunker.process_file = AsyncMock(side_effect=ValueError("Unsupported file type: test.exe"))

            with patch("src.core.config.settings.ADMIN_API_TOKEN", "valid-token"):
                files = {"file": ("test.exe", b"binary", "application/octet-stream")}
                headers = {"Authorization": "Bearer valid-token"}

                response = client.post(
                    f"/api/projects/{project_id}/knowledge",
                    files=files,
                    headers=headers
                )

        assert response.status_code == 400
        assert response.json()["detail"] == "Unsupported file type: test.exe"

    def test_upload_file_read_error(self, client, mock_project_repo):
        """Ошибка чтения файла"""
        project_id = str(uuid4())
        mock_project_repo.project_exists.return_value = True

        # Патчим read метод UploadFile, чтобы выбросить исключение
        with patch("starlette.datastructures.UploadFile.read", side_effect=Exception("read error")):
            with patch("src.core.config.settings.ADMIN_API_TOKEN", "valid-token"):
                with patch("src.api.knowledge.logger") as mock_logger:
                    files = {"file": ("test.txt", b"content", "text/plain")}
                    headers = {"Authorization": "Bearer valid-token"}

                    response = client.post(
                        f"/api/projects/{project_id}/knowledge",
                        files=files,
                        headers=headers
                    )

        assert response.status_code == 400
        assert response.json()["detail"] == "Could not read file"
        mock_logger.error.assert_called_once()

    def test_upload_chunking_error(self, client, mock_project_repo):
        """Ошибка при разбиении на чанки"""
        project_id = str(uuid4())
        mock_project_repo.project_exists.return_value = True

        with patch("src.api.knowledge.ChunkerService") as MockChunker:
            mock_chunker = AsyncMock()
            MockChunker.return_value = mock_chunker
            mock_chunker.process_file = AsyncMock(side_effect=ValueError("Invalid PDF structure"))

            with patch("src.core.config.settings.ADMIN_API_TOKEN", "valid-token"):
                files = {"file": ("test.pdf", b"%PDF-1.4...", "application/pdf")}
                headers = {"Authorization": "Bearer valid-token"}

                response = client.post(
                    f"/api/projects/{project_id}/knowledge",
                    files=files,
                    headers=headers
                )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid PDF structure"

    def test_upload_embedding_error(self, client, mock_project_repo, mock_pool):
        """Ошибка генерации эмбеддинга (обработанная)"""
        project_id = str(uuid4())
        mock_project_repo.project_exists.return_value = True

        with patch("src.api.knowledge.ChunkerService") as MockChunker:
            mock_chunker = AsyncMock()
            MockChunker.return_value = mock_chunker
            mock_chunker.process_file = AsyncMock(return_value=[{"content": "chunk"}])

            with patch("src.api.knowledge.embed_text") as mock_embed:
                mock_embed.side_effect = Exception("Model error")

                with patch("src.core.config.settings.ADMIN_API_TOKEN", "valid-token"):
                    files = {"file": ("test.txt", b"content", "text/plain")}
                    headers = {"Authorization": "Bearer valid-token"}

                    response = client.post(
                        f"/api/projects/{project_id}/knowledge",
                        files=files,
                        headers=headers
                    )

        assert response.status_code == 500
        assert response.json()["detail"] == "Embedding service error"

    def test_upload_unauthorized_missing_token(self, client):
        """Отсутствует токен"""
        project_id = str(uuid4())
        files = {"file": ("test.txt", b"content", "text/plain")}
        response = client.post(f"/api/projects/{project_id}/knowledge", files=files)
        assert response.status_code == 401
        assert response.json()["detail"] == "Authorization header required"

    def test_upload_unauthorized_invalid_token(self, client):
        """Неверный токен"""
        project_id = str(uuid4())
        with patch("src.core.config.settings.ADMIN_API_TOKEN", "correct-token"):
            files = {"file": ("test.txt", b"content", "text/plain")}
            headers = {"Authorization": "Bearer wrong-token"}
            response = client.post(
                f"/api/projects/{project_id}/knowledge",
                files=files,
                headers=headers
            )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid admin token"
