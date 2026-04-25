from src.application.dto.runtime_dto import (
    GraphExecutionRequestDto,
    GraphExecutionResultDto,
    MessageProcessingOutcomeDto,
    ProjectRuntimeContextDto,
)


def test_project_runtime_context_dto_normalizes_missing_sections():
    dto = ProjectRuntimeContextDto.from_record({"settings": {"brand_name": "Acme"}})

    assert dto.to_dict() == {
        "settings": {"brand_name": "Acme"},
        "policies": {},
        "limits": {},
        "integrations": [],
        "channels": [],
    }


def test_message_processing_outcome_dto_preserves_text_and_delivery_flag():
    dto = MessageProcessingOutcomeDto.create("ok", delivered=True)

    assert dto.text == "ok"
    assert dto.delivered is True


def test_graph_execution_request_dto_keeps_runtime_context():
    runtime_context = ProjectRuntimeContextDto(limits={"fallback_model": "llama"})

    dto = GraphExecutionRequestDto(
        project_id="project-1",
        thread_id="thread-1",
        chat_id=123,
        question="hello",
        runtime_context=runtime_context,
        trace_id="trace-1",
    )

    assert dto.project_id == "project-1"
    assert dto.question == "hello"
    assert dto.runtime_context.to_dict()["limits"] == {"fallback_model": "llama"}


def test_graph_execution_result_dto_reads_graph_delivery_flag():
    dto = GraphExecutionResultDto.from_graph_state({"message_sent": True})

    assert dto.response_text == ""
    assert dto.delivered is True


def test_graph_execution_result_dto_reads_graph_response_text():
    dto = GraphExecutionResultDto.from_graph_state({"response_text": "hello"})

    assert dto.response_text == "hello"
    assert dto.delivered is False
