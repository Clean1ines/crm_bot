from src.application.dto.knowledge_dto import KnowledgeUploadResultDto


def test_knowledge_upload_result_dto_serializes_stably():
    dto = KnowledgeUploadResultDto.create(message="Uploaded 2 chunks", chunks=2)

    assert dto.to_dict() == {
        "message": "Uploaded 2 chunks",
        "chunks": 2,
    }
