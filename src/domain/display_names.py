from __future__ import annotations


_EMPTY_NAME_MARKERS = frozenset({"", "none", "null", "undefined"})


def normalize_display_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if normalized.lower() in _EMPTY_NAME_MARKERS:
        return None
    return normalized


def join_name_parts(
    first_name: object | None,
    last_name: object | None,
) -> str | None:
    parts = [
        part
        for part in (
            normalize_display_text(first_name),
            normalize_display_text(last_name),
        )
        if part
    ]
    if not parts:
        return None
    return " ".join(parts)


def normalize_username(username: object | None) -> str | None:
    normalized = normalize_display_text(username)
    if not normalized:
        return None
    return normalized if normalized.startswith("@") else f"@{normalized}"


def build_display_name(
    *,
    full_name: object | None = None,
    first_name: object | None = None,
    last_name: object | None = None,
    username: object | None = None,
    email: object | None = None,
    fallback: str,
) -> str:
    return (
        normalize_display_text(full_name)
        or join_name_parts(first_name, last_name)
        or normalize_username(username)
        or normalize_display_text(email)
        or fallback
    )
