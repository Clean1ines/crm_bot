from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = (
    ROOT / "src",
    ROOT / "tests",
    ROOT / "docs",
    ROOT / "frontend",
)
ALLOWLIST_PATHS = {
    Path(__file__).resolve(),
}

FORBIDDEN_PATTERNS = (
    "CLUSTER_PREVIEW_READY",
    "BuildClusterPreview",
    "PauseForClusterContractReview",
    "ClusterPreviewReady",
    "ClusterContractReviewRequired",
    "build_cluster_preview",
    "pause_for_cluster_contract_review",
    "cluster_preview_ready",
    "cluster_contract_review_required",
)
_PATTERN = re.compile("|".join(re.escape(pattern) for pattern in FORBIDDEN_PATTERNS))


def test_legacy_cluster_preview_contract_names_are_absent() -> None:
    violations: list[str] = []

    for scan_root in SCAN_ROOTS:
        if not scan_root.exists():
            continue
        for path in scan_root.rglob("*"):
            if not path.is_file():
                continue
            if path.resolve() in ALLOWLIST_PATHS:
                continue
            if path.suffix not in {".py", ".md", ".ts", ".tsx", ".sql"}:
                continue
            text = path.read_text(encoding="utf-8")
            for line_number, line in enumerate(text.splitlines(), start=1):
                if _PATTERN.search(line):
                    violations.append(f"{path.relative_to(ROOT)}:{line_number}:{line}")

    assert violations == []
