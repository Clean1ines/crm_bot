from src.application.dto.knowledge_dto import KnowledgeAnswerDraftDto
from src.domain.project_plane.knowledge_compilation import AnswerCandidate, SourceRef


def test_answer_draft_dto_exposes_surface_fields_from_tags() -> None:
    candidate = AnswerCandidate(
        id='c1',
        document_id='d1',
        project_id='p1',
        compiler_run_id='r1',
        topic_key='t1',
        title='Цена',
        candidate_answer='Стоимость зависит от объёма',
        source_refs=(SourceRef(source_index=1, quote='Стоимость зависит от объёма'),),
        metadata={
            'tags': [
                'surface_key:surface:цена',
                'surface_kind:pricing',
                'answer_scope:ценообразование',
                'parent_surface:surface:что это за продукт',
                'child_surface:surface:возврат средств',
                'short_answer:цена зависит от объёма',
            ],
            'question_variants': ['Сколько стоит?'],
        },
    )

    dto = KnowledgeAnswerDraftDto.from_candidate(candidate)
    payload = dto.to_dict()

    assert payload['is_retrieval_surface'] is True
    assert payload['surface_key'] == 'surface:цена'
    assert payload['surface_kind'] == 'pricing'
    assert payload['answer_scope'] == 'ценообразование'
    assert payload['parent_surface_keys'] == ['surface:что это за продукт']
    assert payload['child_surface_keys'] == ['surface:возврат средств']
    assert payload['short_answer'] == 'цена зависит от объёма'
