from pathlib import Path
import ast


LEGACY_REPO_METHODS = {
    "get_project_by_id",
    "get_project_configuration",
    "get_project_members",
    "get_projects_for_user",
}


def _iter_py_files(*roots: str):
    for root in roots:
        yield from Path(root).rglob("*.py")


def _base_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _base_name(node.value)
    if isinstance(node, ast.Call):
        return _base_name(node.func)
    return None


def test_application_and_interfaces_do_not_call_legacy_project_repo_facades():
    violations = []

    for path in _iter_py_files("src/application", "src/interfaces"):
        tree = ast.parse(path.read_text(), filename=str(path))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in LEGACY_REPO_METHODS:
                continue

            base = _base_name(node.func.value)

            # Разрешаем application/http методы типа:
            # project_queries.get_project_configuration(...)
            # Запрещаем именно repo/mock_repo/self.repo.<legacy>()
            if base in {"repo", "mock_repo", "project_repo"}:
                violations.append(
                    f"{path}:{node.lineno} calls {base}.{node.func.attr}("
                )

            if isinstance(node.func.value, ast.Attribute):
                if node.func.value.attr == "repo":
                    violations.append(
                        f"{path}:{node.lineno} calls *.repo.{node.func.attr}("
                    )

    assert not violations, "\n".join(violations)


def test_application_has_no_async_contract_adapters():
    forbidden = {
        "_resolve(",
        "asyncio.iscoroutine",
        "iscoroutine(",
    }

    violations = []

    for path in _iter_py_files("src/application"):
        text = path.read_text()
        for token in forbidden:
            if token in text:
                violations.append(f"{path} contains {token}")

    assert not violations, "\n".join(violations)
