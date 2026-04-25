from pathlib import Path
import ast


LEGACY_REPO_METHODS = {
    "get_project_by_id",
    "get_project_configuration",
    "get_project_members",
    "get_projects_for_user",
}

CHECK_ROOTS = [
    Path("src/application"),
    Path("src/interfaces"),
    Path("tests/api"),
]


def _attr_root_name(node: ast.AST) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    if isinstance(node, ast.Name):
        return node.id
    return None


def iter_python_files():
    for root in CHECK_ROOTS:
        yield from root.rglob("*.py")


def test_no_application_or_api_code_calls_legacy_project_repo_facades():
    violations = []

    for path in iter_python_files():
        tree = ast.parse(path.read_text(), filename=str(path))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            func = node.func
            if not isinstance(func, ast.Attribute):
                continue

            if func.attr not in LEGACY_REPO_METHODS:
                continue

            root_name = _attr_root_name(func.value) or ""
            full_expr = ast.unparse(func.value)

            # Ловим именно repo/project_repo/mock_project_repo/self.repo,
            # но не project_queries.get_project_configuration(...)
            if "repo" not in root_name.lower() and ".repo" not in full_expr.lower():
                continue

            violations.append(
                f"{path}:{node.lineno}:{node.col_offset} {full_expr}.{func.attr}(...)"
            )

    assert not violations, (
        "Legacy project repository facade calls found:\n" + "\n".join(violations)
    )
