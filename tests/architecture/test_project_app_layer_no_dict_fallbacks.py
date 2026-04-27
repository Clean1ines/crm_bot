from pathlib import Path


FORBIDDEN_PATTERNS = [
    "isinstance(project, ProjectSummaryView)",
    "isinstance(member, ProjectMemberView)",
    "else project",
    "else member",
    "from_record(project)",
    "from_record(member)",
    "member.get(",
    "project: dict",
]


def test_project_app_services_do_not_accept_typed_or_dict_fallbacks():
    files = [
        Path("src/application/services/project_command_service.py"),
        Path("src/application/services/knowledge_service.py"),
        Path("src/application/services/platform_bot_service.py"),
    ]

    violations = []

    for path in files:
        text = path.read_text()
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in text:
                violations.append(f"{path}: forbidden fallback pattern: {pattern}")

    assert not violations, (
        "Project app-layer typed/dict fallback debt found:\n" + "\n".join(violations)
    )
