from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


FORBIDDEN_LIVE_PATHS = (
    Path("src/application/rag_eval"),
    Path("src/interfaces/http/rag_eval.py"),
    Path("src/infrastructure/db/repositories/rag_eval_repository.py"),
    Path("src/infrastructure/" + "rag_eval"),
    Path("src/interfaces/composition/rag_eval_answerer.py"),
    Path("tests/application/rag_eval"),
    Path("tests/application/rag_eval"),
)


FORBIDDEN_LIVE_TOKENS = (
    "src." + "application." + "rag_eval",
    "application." + "rag_eval",
    "Rag" + "EvalRunner",
    "RagEvalDataset",
    "RagEvalResult",
    "RagQualityReport",
    "src.infrastructure.db.repositories." + "rag_eval_repository",
    "from src.infrastructure.db.repositories import " + "rag_eval_repository",
    "from src.infrastructure.db.repositories." + "rag_eval_repository",
    "interfaces.http." + "rag_eval",
    "/api/" + "rag-eval",
)


FORBIDDEN_WORKBENCH_RAG_EVAL_TOKENS = (
    "answer_text",
    "knowledge_" + "retrieval_" + "surface",
    "knowledge_workbench_surfaces",
)


LIVE_SCAN_ROOTS = (
    Path("src"),
    Path("frontend/src"),
)


def _iter_live_files() -> tuple[Path, ...]:
    result: list[Path] = []
    for root in LIVE_SCAN_ROOTS:
        absolute_root = ROOT / root
        if not absolute_root.exists():
            continue
        for path in absolute_root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in {".py", ".ts", ".tsx", ".txt"}:
                continue
            result.append(path)
    return tuple(result)


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def test_legacy_rag_eval_live_paths_do_not_exist() -> None:
    existing = tuple(
        _relative(ROOT / path)
        for path in FORBIDDEN_LIVE_PATHS
        if (ROOT / path).exists()
    )

    assert existing == ()


def test_live_code_does_not_reference_legacy_rag_eval_surface() -> None:
    offenders: list[str] = []

    for path in _iter_live_files():
        relative = _relative(path)

        if relative == "tests/architecture/test_no_legacy_rag_eval_surface.py":
            continue

        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_LIVE_TOKENS:
            if token in text:
                offenders.append(f"{relative}: {token}")

    assert offenders == []


def test_workbench_rag_eval_does_not_use_legacy_retrieval_or_answer_text() -> None:
    offenders: list[str] = []
    workbench_roots = (
        ROOT / "src/contexts/knowledge_workbench/rag_eval",
        ROOT / "frontend/src/pages/rag-eval",
    )

    for root in workbench_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".ts", ".tsx", ".txt"}:
                continue
            text = path.read_text(encoding="utf-8")
            for token in FORBIDDEN_WORKBENCH_RAG_EVAL_TOKENS:
                if token in text:
                    offenders.append(f"{_relative(path)}: {token}")

    assert offenders == []
