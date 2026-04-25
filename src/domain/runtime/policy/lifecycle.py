VALID_LIFECYCLES = (
    "cold",
    "interested",
    "warm",
    "handoff_to_manager",
    "active_client",
    "angry",
)

DEFAULT_LIFECYCLE = "cold"


def normalize_lifecycle(lifecycle: str | None) -> str:
    value = (lifecycle or "").strip().lower()
    if value == "hot":
        return "warm"
    if value in VALID_LIFECYCLES:
        return value
    return DEFAULT_LIFECYCLE
