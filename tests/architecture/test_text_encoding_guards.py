from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

# Common mojibake fragments produced when UTF-8 text is decoded with cp1251/win-1252
# and then re-saved. Kept intentionally narrow to reduce false positives.
MOJIBAKE_MARKERS = (
    "РІР‚",
    "РІСљ",
    "РІСњ",
    "РїС‘",
    "Р Р†РЎ",
    "РЎР‚РЎ",
    "Р СџРЎ",
    "Р В ",
    "вЂ“",
    "вЏі",
    "Р’Р°С€",
    "РЎРµР№С‡Р°СЃ",
    "РћР¶РёРґР°Р№С‚Рµ",
)


def test_production_code_contains_no_common_mojibake_markers() -> None:
    offenders: list[str] = []

    for path in SRC.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue

        text = path.read_text(encoding="utf-8")
        hits = [marker for marker in MOJIBAKE_MARKERS if marker in text]
        if hits:
            rel = path.relative_to(ROOT).as_posix()
            offenders.append(f"{rel}: {hits}")

    assert offenders == []
