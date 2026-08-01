from pathlib import Path


def test_generated_typescript_ticket_resolution_status_is_typed_union():
    schema = Path("frontend/src/shared/api/generated/schema.ts").read_text(
        encoding="utf-8"
    )

    expected = 'status: "pending" | "generated" | "edited" | "failed" | "missing";'
    assert expected in schema
