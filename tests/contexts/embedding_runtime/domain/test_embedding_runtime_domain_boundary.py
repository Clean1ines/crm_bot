from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
EMBEDDING_RUNTIME_DOMAIN = ROOT / "src" / "contexts" / "embedding_runtime" / "domain"


def test_embedding_runtime_domain_has_no_infrastructure_or_workbench_terms() -> None:
    forbidden_markers = (
        "provider",
        "httpx",
        "Groq",
        "groq",
        "Qwen",
        "qwen",
        "Postgres",
        "postgres",
        "pgvector",
        "knowledge_workbench",
        "DraftClaim",
        "Claim",
        "Surface",
        "surface",
    )

    offenders: list[str] = []
    for path in EMBEDDING_RUNTIME_DOMAIN.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            if marker in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {marker!r}")

    assert not offenders
