from __future__ import annotations

import ast
from pathlib import Path


RAG_EVAL_APPLICATION_ROOT = Path(
    "src/contexts/knowledge_workbench/rag_eval/application"
)
RAG_EVAL_PLANNER_MODULES = (
    Path(
        "src/contexts/knowledge_workbench/rag_eval/application/workflows/"
        "plan_workbench_rag_eval_question_generation_work.py"
    ),
    Path(
        "src/contexts/knowledge_workbench/rag_eval/application/workflows/"
        "plan_workbench_rag_eval_adjudication_work.py"
    ),
)


def test_rag_eval_planners_do_not_hand_build_execution_capacity_contract() -> None:
    forbidden_keys = {"budget_contract_version", "model_tpm_limit"}

    for module_path in RAG_EVAL_PLANNER_MODULES:
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            literal_keys = {
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            assert literal_keys.isdisjoint(forbidden_keys), module_path


def test_rag_eval_application_does_not_import_llm_runtime_infrastructure() -> None:
    offenders: list[str] = []

    for module_path in RAG_EVAL_APPLICATION_ROOT.rglob("*.py"):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module_name = _imported_module_name(node)
            if module_name is None:
                continue
            if (
                module_name.startswith("src.contexts.llm_runtime.infrastructure")
                or ".providers." in module_name
            ):
                offenders.append(f"{module_path}: {module_name}")

    assert not offenders, "\n".join(offenders)


def _imported_module_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.ImportFrom):
        return node.module
    if isinstance(node, ast.Import):
        return node.names[0].name if node.names else None
    return None
