import pytest
from src.domain.control_plane.project_views import ProjectSummaryView
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from uuid import uuid4
import io

from src.interfaces.http.app import app
from src.interfaces.http.dependencies import get_project_repo, get_pool, get_user_repository


TEST_USER_ID = "knowledge-user-id"


@pytest.fixture
def mock_project_repo():
    repo = AsyncMock()
    repo.project_exists = AsyncMock()
    repo.user_has_project_role = AsyncMock(return_value=True)
    return repo


@pytest.fixture
def mock_user_repo():
    repo = AsyncMock()
    repo.is_platform_admin = AsyncMock(return_value=False)
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
def override_dependencies(mock_project_repo, mock_pool, mock_user_repo):
    original_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_project_repo] = lambda: mock_project_repo
    app.dependency_overrides[get_pool] = lambda: mock_pool
    app.dependency_overrides[get_user_repository] = lambda: mock_user_repo
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
        with patch("src.interfaces.http.knowledge.ChunkerService") as MockChunker:
            mock_chunker = AsyncMock()
            MockChunker.return_value = mock_chunker
            mock_chunker.process_file = AsyncMock(return_value=chunks)

            with patch("src.interfaces.http.knowledge.KnowledgeRepository") as MockRepo:
                mock_repo = AsyncMock()
                MockRepo.return_value = mock_repo
                mock_repo.create_document = AsyncMock(return_value="doc-1")
                mock_repo.add_knowledge_batch = AsyncMock(return_value=2)

                with patch("src.interfaces.http.knowledge.jwt.decode", return_value={"sub": TEST_USER_ID}):
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
        mock_repo.create_document.assert_awaited_once_with(
            project_id=project_id,
            file_name="test.txt",
            file_size=len(b"Test content"),
            uploaded_by=TEST_USER_ID,
        )
        mock_repo.add_knowledge_batch.assert_awaited_once_with(
            project_id, chunks, document_id="doc-1"
        )

    def test_upload_success_pdf(self, client, mock_project_repo, mock_pool):
        """Успешная загрузка PDF файла"""
        project_id = str(uuid4())
        mock_project_repo.project_exists.return_value = True

        with patch("src.interfaces.http.knowledge.ChunkerService") as MockChunker:
            mock_chunker = AsyncMock()
            MockChunker.return_value = mock_chunker
            mock_chunker.process_file = AsyncMock(return_value=[{"content": "pdf chunk"}])

            with patch("src.interfaces.http.knowledge.KnowledgeRepository") as MockRepo:
                mock_repo = AsyncMock()
                MockRepo.return_value = mock_repo
                mock_repo.create_document = AsyncMock(return_value="doc-1")
                mock_repo.add_knowledge_batch = AsyncMock(return_value=1)

                with patch("src.interfaces.http.knowledge.jwt.decode", return_value={"sub": TEST_USER_ID}):
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

        with patch("src.interfaces.http.knowledge.ChunkerService") as MockChunker:
            mock_chunker = AsyncMock()
            MockChunker.return_value = mock_chunker
            mock_chunker.process_file = AsyncMock(return_value=[])

            with patch("src.interfaces.http.knowledge.jwt.decode", return_value={"sub": TEST_USER_ID}):
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

        with patch("src.interfaces.http.knowledge.jwt.decode", return_value={"sub": TEST_USER_ID}):
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
        with patch("src.interfaces.http.knowledge.jwt.decode", return_value={"sub": TEST_USER_ID}):
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

        with patch("src.interfaces.http.knowledge.ChunkerService") as MockChunker:
            mock_chunker = AsyncMock()
            MockChunker.return_value = mock_chunker
            mock_chunker.process_file = AsyncMock(side_effect=ValueError("Unsupported file type: test.exe"))

            with patch("src.interfaces.http.knowledge.jwt.decode", return_value={"sub": TEST_USER_ID}):
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
            with patch("src.interfaces.http.knowledge.jwt.decode", return_value={"sub": TEST_USER_ID}):
                with patch("src.interfaces.http.knowledge.logger") as mock_logger:
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

        with patch("src.interfaces.http.knowledge.ChunkerService") as MockChunker:
            mock_chunker = AsyncMock()
            MockChunker.return_value = mock_chunker
            mock_chunker.process_file = AsyncMock(side_effect=ValueError("Invalid PDF structure"))

            with patch("src.interfaces.http.knowledge.jwt.decode", return_value={"sub": TEST_USER_ID}):
                files = {"file": ("test.pdf", b"%PDF-1.4...", "application/pdf")}
                headers = {"Authorization": "Bearer valid-token"}

                response = client.post(
                    f"/api/projects/{project_id}/knowledge",
                    files=files,
                    headers=headers
                )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid PDF structure"

    def test_upload_persistence_error(self, client, mock_project_repo, mock_pool):
        """Ошибка сохранения knowledge"""
        project_id = str(uuid4())
        mock_project_repo.project_exists.return_value = True
        error_client = TestClient(app, raise_server_exceptions=False)

        with patch("src.interfaces.http.knowledge.ChunkerService") as MockChunker:
            mock_chunker = AsyncMock()
            MockChunker.return_value = mock_chunker
            mock_chunker.process_file = AsyncMock(return_value=[{"content": "chunk"}])

            with patch("src.interfaces.http.knowledge.KnowledgeRepository") as MockRepo:
                mock_repo = AsyncMock()
                MockRepo.return_value = mock_repo
                mock_repo.create_document = AsyncMock(side_effect=Exception("DB error"))

                with patch("src.interfaces.http.knowledge.jwt.decode", return_value={"sub": TEST_USER_ID}):
                    files = {"file": ("test.txt", b"content", "text/plain")}
                    headers = {"Authorization": "Bearer valid-token"}

                    response = error_client.post(
                        f"/api/projects/{project_id}/knowledge",
                        files=files,
                        headers=headers
                    )

        assert response.status_code == 500

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
        files = {"file": ("test.txt", b"content", "text/plain")}
        headers = {"Authorization": "Bearer wrong-token"}
        response = client.post(
            f"/api/projects/{project_id}/knowledge",
            files=files,
            headers=headers
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid token"

    def test_upload_authorized_via_project_owner_jwt(self, client, mock_project_repo, mock_pool):
        project_id = str(uuid4())
        user_id = str(uuid4())
        mock_project_repo.user_has_project_role = AsyncMock(return_value=True)

        with patch("src.interfaces.http.knowledge.jwt.decode", return_value={"sub": user_id}):
            with patch("src.interfaces.http.knowledge.ChunkerService") as MockChunker:
                mock_chunker = AsyncMock()
                MockChunker.return_value = mock_chunker
                mock_chunker.process_file = AsyncMock(return_value=[{"content": "chunk"}])

                with patch("src.interfaces.http.knowledge.KnowledgeRepository") as MockRepo:
                    mock_repo = AsyncMock()
                    MockRepo.return_value = mock_repo
                    mock_repo.create_document = AsyncMock(return_value="doc-1")
                    mock_repo.add_knowledge_batch = AsyncMock(return_value=1)

                    response = client.post(
                        f"/api/projects/{project_id}/knowledge",
                        files={"file": ("test.txt", b"content", "text/plain")},
                        headers={"Authorization": "Bearer jwt-token"},
                    )

        assert response.status_code == 200
        mock_project_repo.user_has_project_role.assert_awaited_once_with(project_id, user_id, ["owner", "admin"])
        mock_repo.create_document.assert_awaited_once_with(
            project_id=project_id,
            file_name="test.txt",
            file_size=len(b"content"),
            uploaded_by=user_id,
        )

    def test_upload_authorized_via_platform_admin_jwt(
        self,
        client,
        mock_project_repo,
        mock_user_repo,
    ):
        project_id = str(uuid4())
        user_id = str(uuid4())
        mock_project_repo.project_exists.return_value = True
        mock_project_repo.user_has_project_role = AsyncMock(return_value=False)
        mock_user_repo.is_platform_admin = AsyncMock(return_value=True)

        with patch("src.interfaces.http.knowledge.jwt.decode", return_value={"sub": user_id}):
            with patch("src.interfaces.http.knowledge.ChunkerService") as MockChunker:
                mock_chunker = AsyncMock()
                MockChunker.return_value = mock_chunker
                mock_chunker.process_file = AsyncMock(return_value=[{"content": "chunk"}])

                with patch("src.interfaces.http.knowledge.KnowledgeRepository") as MockRepo:
                    mock_repo = AsyncMock()
                    MockRepo.return_value = mock_repo
                    mock_repo.create_document = AsyncMock(return_value="doc-1")
                    mock_repo.add_knowledge_batch = AsyncMock(return_value=1)

                    response = client.post(
                        f"/api/projects/{project_id}/knowledge",
                        files={"file": ("test.txt", b"content", "text/plain")},
                        headers={"Authorization": "Bearer jwt-token"},
                    )

        assert response.status_code == 200
        mock_user_repo.is_platform_admin.assert_awaited_once_with(user_id)
        mock_project_repo.user_has_project_role.assert_not_awaited()
        mock_repo.create_document.assert_awaited_once_with(
            project_id=project_id,
            file_name="test.txt",
            file_size=len(b"content"),
            uploaded_by=user_id,
        )

    def test_upload_forbidden_for_non_owner_non_admin(self, client, mock_project_repo):
        project_id = str(uuid4())
        user_id = str(uuid4())
        mock_project_repo.user_has_project_role = AsyncMock(return_value=False)
        mock_project_repo.get_project_view = AsyncMock(return_value=ProjectSummaryView(
            id=project_id,
            name="Test",
            is_pro_mode=False,
            user_id=str(uuid4()),
            client_bot_username=None,
            manager_bot_username=None,
            access_role=None,
        ))

        with patch("src.interfaces.http.knowledge.jwt.decode", return_value={"sub": user_id}):
            response = client.post(
                f"/api/projects/{project_id}/knowledge",
                files={"file": ("test.txt", b"content", "text/plain")},
                headers={"Authorization": "Bearer jwt-token"},
            )

        assert response.status_code == 403
        assert response.json()["detail"] == "Insufficient permissions"
