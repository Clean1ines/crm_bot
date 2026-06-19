from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path


def build_draft_claim_compaction_provider_messages(
    *,
    prompt_file_name: str,
    payload: Mapping[str, object],
) -> tuple[dict[str, str], ...]:
    if not isinstance(prompt_file_name, str) or not prompt_file_name.strip():
        raise ValueError("prompt_file_name must be non-empty")
    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / prompt_file_name
    if not prompt_path.is_file():
        raise FileNotFoundError(f"Compaction prompt is missing: {prompt_path}")
    prompt_text = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt_text:
        raise ValueError("compaction prompt must be non-empty")
    return (
        {"role": "system", "content": prompt_text},
        {
            "role": "user",
            "content": json.dumps(
                dict(payload),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        },
    )
