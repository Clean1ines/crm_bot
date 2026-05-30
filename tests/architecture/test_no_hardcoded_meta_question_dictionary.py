from __future__ import annotations

from pathlib import Path


def test_no_hardcoded_meta_question_dictionary() -> None:
    source = Path(
        "src/application/services/knowledge_compiled_entry_cleanup.py"
    ).read_text(
        encoding="utf-8",
    )
    section = source[
        source.index("def _mechanically_cleanup_compiled_entries") : source.index(
            "def _entry_question_intent_fingerprints"
        )
    ]

    forbidden_snippets = (
        "suspicious_meta",
        "meta_entry",
        "meta_question",
        "bad_question",
        "служебный",
        "служебные",
        "метавопрос",
        "не смешивать",
    )
    for snippet in forbidden_snippets:
        assert snippet not in section
