from __future__ import annotations

import inspect

from src.interfaces.composition import knowledge_extraction_workflow_resume as resume


def test_resume_factory_wires_route_catalog_into_capacity_window_admission_pass() -> (
    None
):
    source = inspect.getsource(resume.make_knowledge_extraction_workflow_resume)

    assert "route_catalog = default_groq_llm_model_route_catalog()" in source
    assert "capacity_window_admission_route_catalog=route_catalog" in source


def test_capacity_window_admission_pass_builder_uses_transaction_bound_repositories() -> (
    None
):
    source = inspect.getsource(resume._capacity_window_admission_pass_for_transaction)

    assert "PostgresCapacityAdmissionWorkItemSelector(connection)" in source
    assert "PostgresWorkItemLeaseRepository(connection)" in source
    assert "PostgresCapacityAdmissionProjectionAdmitter(connection)" in source
    assert "PostgresLlmRouteCapacityReservationRepository(" in source
    assert "PostgresWorkItemAttemptDispatchRepository(" in source
    assert "_PostgresCapacityWindowAdmissionActiveLeaseInspector(" in source
