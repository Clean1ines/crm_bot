from pathlib import Path


ADR_PATH = Path("docs/architecture/capacity_admission_queue_runtime_adr.md")
PREPARE_PATH = Path("src/interfaces/composition/prepare_llm_dispatch_batch.py")


def test_capacity_admission_queue_runtime_adr_exists() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")

    assert "Capacity Admission Queue Runtime" in text
    assert "capacity_admission_queue" in text
    assert "CapacityAdmissionWorkItemProjection" in text
    assert "CapacityAdmissionLane" in text
    assert "DueWorkQueueChanged" in text
    assert "CapacityWindowChanged" in text
    assert "AdmissionDispatcher" in text
    assert "CapacityWindowAdmissionPass" in text


def test_capacity_admission_queue_adr_forbids_requested_items_candidate_scan() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")

    assert "`requested_items` may be used only as an optional safety cap" in text
    assert "It must not decide how many due candidates are inspected." in text
    assert (
        "`peek_due_work_items(requested_items=N)` as the main admission candidate source"
        in text
    )
    assert "bounded overfetch multipliers" in text
    assert "page scan as the semantic solution to capacity fitting" in text
    assert "Admission must search an indexed admission projection" in text


def test_capacity_admission_queue_adr_defines_lane_not_affected_window() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")

    assert "Admission is lane-based, not window-addressed" in text
    assert "does not target one specific CapacityWindow" in text
    assert "An Admission Lane is identified by at least" in text
    assert "`work_kind`" in text
    assert "`provider`" in text
    assert "`model_ref`" in text
    assert (
        "Atomic capacity reservation and WorkItem lease decide which window wins"
        in text
    )


def test_capacity_admission_queue_adr_defines_retry_ready_priority() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")

    assert "Find a fitting `retryable_failed` candidate" in text
    assert "find a fitting `ready` candidate" in text
    assert "If many fitting retries exist, deterministic order is enough" in text


def test_capacity_admission_queue_adr_defines_split_and_leased_retry_semantics() -> (
    None
):
    text = ADR_PATH.read_text(encoding="utf-8")

    assert "`split_superseded` means the parent WorkItem is no longer eligible" in text
    assert "child WorkItems that are `ready`" in text
    assert "one `DueWorkQueueChanged` event for the lane" in text
    assert "`leased -> retryable_failed`" in text
    assert "does not mean the returning WorkItem must be selected directly" in text
    assert "mark the lane dirty" in text


def test_capacity_admission_queue_adr_defines_durable_source_of_truth() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")

    assert "Postgres is the durable source of truth." in text
    assert (
        "`LISTEN/NOTIFY` or in-process notifications may be used only as wakeups."
        in text
    )
    assert "They must never be the only source of truth." in text
    assert "A dispatcher must be able to crash and resume from durable tables." in text
    assert "make duplicate admission passes harmless" in text


def test_capacity_admission_queue_adr_is_not_production_code() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")

    assert "ADR-1 does not implement:" in text
    assert "new production tables" in text
    assert "new dispatcher" in text
    assert "new repository" in text
    assert "provider API calls" in text


def test_forbidden_prefix_scan_cw3_markers_are_absent_from_prepare_hot_path() -> None:
    text = PREPARE_PATH.read_text(encoding="utf-8")

    assert "_candidate_scan_limit" not in text
    assert "_CANDIDATE_SCAN_MULTIPLIER" not in text
    assert "_CANDIDATE_SCAN_EXTRA_CAP" not in text
    assert "candidate_scan_limit" not in text
