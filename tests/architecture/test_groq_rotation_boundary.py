from __future__ import annotations

from pathlib import Path


def test_src_code_does_not_bypass_groq_keyring_with_primary_key() -> None:
    root = Path(__file__).resolve().parents[2]
    allowed = {
        root / "src/infrastructure/config/settings.py",
        root / "src/infrastructure/llm/groq_keyring.py",
    }

    offenders: list[str] = []
    for path in (root / "src").rglob("*.py"):
        if path in allowed:
            continue

        text = path.read_text(encoding="utf-8")
        if "api_key=settings.GROQ_API_KEY" in text:
            offenders.append(str(path.relative_to(root)))

    assert not offenders, "Groq clients must use groq_keyring, offenders: " + ", ".join(
        offenders
    )
