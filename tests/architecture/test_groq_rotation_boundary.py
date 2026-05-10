from __future__ import annotations

import re
from pathlib import Path


def test_runtime_code_does_not_bypass_groq_rotation() -> None:
    root = Path(__file__).resolve().parents[2]
    allowed = {
        root / "src/infrastructure/config/settings.py",
        root / "src/infrastructure/llm/groq_keyring.py",
    }

    forbidden_patterns = {
        r"(?<!Rotating)AsyncGroq\(": "direct AsyncGroq constructor",
        r"(?<!Async)Groq\(": "direct Groq constructor",
        r"current_groq_api_key\(": "snapshot Groq key usage",
        r"api_key\s*=\s*settings\.GROQ_API_KEY": "primary Groq key passed directly",
    }

    violations: list[str] = []

    for path in (root / "src").rglob("*.py"):
        if path in allowed:
            continue

        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(root)

        for pattern, reason in forbidden_patterns.items():
            if re.search(pattern, text):
                violations.append(f"{rel}: {reason}: {pattern}")

    assert not violations, (
        "Groq calls must go through the rotating keyring adapter only:\n"
        + "\n".join(violations)
    )
