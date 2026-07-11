from __future__ import annotations

import unicodedata


def normalize_workbench_rag_eval_question(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("question must be str")

    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    characters: list[str] = []
    previous_was_space = False

    for character in normalized:
        category = unicodedata.category(character)
        if character.isspace() or category.startswith("P"):
            if characters and not previous_was_space:
                characters.append(" ")
                previous_was_space = True
            continue
        characters.append(character)
        previous_was_space = False

    return "".join(characters).strip()
