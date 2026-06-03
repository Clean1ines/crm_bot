from __future__ import annotations

from pathlib import Path


RELEVANT_PATHS = (
    Path("src/infrastructure/queue/handlers/workbench_parallel_processing.py"),
    Path("src/infrastructure/queue/workbench_parallel_queue.py"),
    Path("src/infrastructure/queue/job_types.py"),
    Path("src/infrastructure/queue/job_dispatcher.py"),
    Path("src/infrastructure/queue/worker_loop.py"),
    Path("src/interfaces/composition/faq_workbench_upload.py"),
    Path("src/interfaces/composition/faq_workbench_resume.py"),
)

REMOVED_GATE_FILES = (
    Path("src/infrastructure/queue/workbench_parallel_dispatch_gate.py"),
    Path("tests/infrastructure/queue/test_workbench_parallel_dispatch_gate.py"),
    Path("tests/architecture/test_workbench_parallel_dispatch_gate_boundary.py"),
)


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def test_parallel_processing_has_no_extra_env_feature_gate() -> None:
    for path in REMOVED_GATE_FILES:
        assert not path.exists(), f"obsolete env gate file must be removed: {path}"

    forbidden = (
        "FAQ_WORKBENCH_PARALLEL_PROCESSING_ENABLED",
        "parallel_workbench_processing_enabled",
        "ParallelWorkbenchDispatchGate",
        "dispatch_parallel_workbench_processing_if_enabled",
        "BLOCKED_BY_GATE",
    )

    for path in RELEVANT_PATHS:
        if not path.exists():
            continue
        source = _read(path)
        for marker in forbidden:
            assert marker not in source, f"{marker} leaked into {path}"


def test_parallel_processing_safety_is_queue_presence_not_env_gate() -> None:
    queue_source = _read(Path("src/infrastructure/queue/workbench_parallel_queue.py"))
    handler_source = _read(
        Path("src/infrastructure/queue/handlers/workbench_parallel_processing.py")
    )
    upload_source = _read(Path("src/interfaces/composition/faq_workbench_upload.py"))
    resume_source = _read(Path("src/interfaces/composition/faq_workbench_resume.py"))

    assert "enqueue_process_workbench_parallel_processing" in queue_source
    assert "handle_workbench_parallel_processing_job" in handler_source

    assert "enqueue_process_workbench_parallel_processing" not in upload_source
    assert "enqueue_process_workbench_parallel_processing" not in resume_source
    assert "process_workbench_parallel_processing" not in upload_source
    assert "process_workbench_parallel_processing" not in resume_source


def test_parallel_processing_no_env_gate_does_not_restore_legacy_compiler() -> None:
    combined = ""
    for path in RELEVANT_PATHS:
        if path.exists():
            combined += path.read_text(encoding="utf-8")

    forbidden = (
        "knowledge_surface_compiler",
        "knowledge_surface_parallel_graph_compiler",
        "process_knowledge_upload",
        "AnswerCandidate",
        "CandidateCluster",
        "KnowledgeSurfaceCompilerPort",
    )
    for marker in forbidden:
        assert marker not in combined


def test_parallel_processing_no_env_gate_does_not_detour_into_resume_cancel_stop() -> (
    None
):
    # Do not scan faq_workbench_resume.py here: that module legitimately exports
    # resume_workbench_document. This guard is about the parallel production path,
    # not about forbidding the manual resume composition module from existing.
    parallel_runtime_paths = (
        Path("src/infrastructure/queue/handlers/workbench_parallel_processing.py"),
        Path("src/infrastructure/queue/workbench_parallel_queue.py"),
        Path("src/infrastructure/queue/job_types.py"),
        Path("src/infrastructure/queue/job_dispatcher.py"),
        Path("src/infrastructure/queue/worker_loop.py"),
        Path("src/interfaces/composition/faq_workbench_upload.py"),
    )

    combined = ""
    for path in parallel_runtime_paths:
        if path.exists():
            combined += path.read_text(encoding="utf-8")

    forbidden = (
        "resume_workbench",
        "cancel_workbench",
        "stop_workbench",
        "ensure_document_can_be_resumed",
        "decide_processing_cancel_transition",
        "decide_processing_resume_or_recovery_transition",
    )
    for marker in forbidden:
        assert marker not in combined
