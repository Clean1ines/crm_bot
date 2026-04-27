from src.infrastructure.db.repositories.user_repository import (
    _hash_password,
    _verify_password,
)
from src.infrastructure.llm.rag_service import RAGService


def test_verify_password_returns_false_for_malformed_hash():
    assert _verify_password("secret", "not-a-valid-password-hash") is False
    assert _verify_password("secret", "pbkdf2_sha256$bad-iterations$salt$hash") is False
    assert (
        _verify_password("secret", "pbkdf2_sha256$210000$not-base64$also-not-base64")
        is False
    )


def test_verify_password_accepts_valid_hash_and_rejects_wrong_password():
    stored_hash = _hash_password("correct-password")

    assert _verify_password("correct-password", stored_hash) is True
    assert _verify_password("wrong-password", stored_hash) is False


def test_safe_json_extract_returns_empty_list_for_malformed_model_output():
    service = RAGService.__new__(RAGService)

    assert service._safe_json_extract("") == []
    assert service._safe_json_extract("no json here") == []
    assert service._safe_json_extract("[1, broken]") == []


def test_safe_json_extract_returns_integer_indexes_only():
    service = RAGService.__new__(RAGService)

    assert service._safe_json_extract("answer: [1, 2, 3]") == [1, 2, 3]
    assert service._safe_json_extract("answer: [1, 2.5, 3]") == []
