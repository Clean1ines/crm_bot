from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Literal, TypeAlias, cast

from src.application.rag_eval.schemas import (
    JsonObject,
    JsonValue,
    RagEvalResult,
    RagEvalRun,
    RagQualityReport,
    new_eval_id,
)


ReadinessValue: TypeAlias = Literal["ready", "needs_review", "not_ready"]
SHOULD_ANSWER_RATE_KEY = "should_answer_" + "pass_rate"


def _metric_float(metrics: Mapping[str, JsonValue], key: str) -> float:
    value = metrics.get(key)
    if value is None or isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float | str):
        return float(value)
    return 0.0


def _metric_int(metrics: Mapping[str, JsonValue], key: str) -> int:
    value = metrics.get(key)
    if value is None or isinstance(value, bool):
        return 0
    if isinstance(value, int | float | str):
        return int(value)
    return 0


def _result_mode(result: RagEvalResult) -> str:
    mode = result.judge_json.get("mode")
    return str(mode or "answer_quality_eval")


def _all_retrieval_eval(results: list[RagEvalResult]) -> bool:
    return bool(results) and all(
        _result_mode(result) == "retrieval_eval" for result in results
    )


def _retrieval_metrics(results: list[RagEvalResult]) -> JsonObject:
    keys = (
        "retrieval_mode",
        "retrieval_path",
        "query_expansion_enabled",
        "runtime_equivalent",
        "diagnostic",
    )
    for result in results:
        metrics = {
            key: result.judge_json[key] for key in keys if key in result.judge_json
        }
        if metrics:
            return metrics
    return {}


class RagQualityReporter:
    def build_report(self, *, run: RagEvalRun) -> RagQualityReport:
        metrics = self._metrics(run.results)
        score = _metric_float(metrics, "score")
        readiness = self._readiness(score, run.results)
        strengths = self._strengths(metrics)
        problems = self._problems(run.results, metrics)
        recommendations = self._recommendations(run.results, metrics)
        markdown = self._markdown(
            run=run,
            score=score,
            readiness=cast(ReadinessValue, readiness),
            strengths=strengths,
            problems=problems,
            recommendations=recommendations,
            metrics=metrics,
        )

        return RagQualityReport(
            id=new_eval_id("report"),
            run_id=run.id,
            dataset_id=run.dataset_id,
            project_id=run.project_id,
            document_id=run.document_id,
            score=score,
            readiness=cast(ReadinessValue, readiness),
            strengths=strengths,
            problems=problems,
            recommendations=recommendations,
            metrics=metrics,
            markdown=markdown,
        )

    def _metrics(self, results: list[RagEvalResult]) -> JsonObject:
        total = len(results)
        if total == 0:
            return {
                "score": 0.0,
                "total": 0,
                "top1_rate": 0.0,
                "top3_rate": 0.0,
                "top5_rate": 0.0,
                "expected_entry_found_rate": 0.0,
                "answer_supported_rate": 0.0,
                SHOULD_ANSWER_RATE_KEY: 0.0,
                "high_hallucination_risk": 0,
                "wrong_entry_top1": 0,
                "retrieval_eval_count": 0,
            }

        retrieval_eval_count = sum(
            _result_mode(result) == "retrieval_eval" for result in results
        )

        retrieval_metrics = _retrieval_metrics(results)

        return {
            "score": round(sum(result.score for result in results) / total * 100, 2),
            "total": total,
            "top1_rate": round(
                sum(result.top1_hit for result in results) / total * 100, 2
            ),
            "top3_rate": round(
                sum(result.top3_hit for result in results) / total * 100, 2
            ),
            "top5_rate": round(
                sum(result.top5_hit for result in results) / total * 100, 2
            ),
            "expected_entry_found_rate": round(
                sum(result.expected_entry_found for result in results) / total * 100,
                2,
            ),
            "answer_supported_rate": round(
                sum(result.answer_supported for result in results) / total * 100,
                2,
            ),
            SHOULD_ANSWER_RATE_KEY: round(
                sum(result.should_answer_passed for result in results) / total * 100,
                2,
            ),
            "high_hallucination_risk": sum(
                1 for result in results if result.hallucination_risk == "high"
            ),
            "wrong_entry_top1": sum(result.wrong_entry_top1 for result in results),
            "retrieval_eval_count": retrieval_eval_count,
            "by_question_type": dict(
                Counter(result.question.question_type for result in results)
            ),
            **retrieval_metrics,
        }

    def _readiness(self, score: float, results: list[RagEvalResult]) -> str:
        retrieval_only = _all_retrieval_eval(results)
        high_risk = any(result.hallucination_risk == "high" for result in results)
        wrong_top1_count = sum(result.wrong_entry_top1 for result in results)

        if score < 75 or (high_risk and not retrieval_only) or wrong_top1_count >= 3:
            return "not_ready"
        if score < 90 or wrong_top1_count:
            return "needs_review"
        return "ready"

    def _strengths(self, metrics: JsonObject) -> list[str]:
        strengths: list[str] = []

        retrieval_only = _metric_int(metrics, "retrieval_eval_count") == _metric_int(
            metrics, "total"
        )

        if _metric_float(metrics, "top3_rate") >= 85:
            strengths.append("RAG хорошо находит ожидаемые источники в top-3.")

        if retrieval_only:
            if _metric_float(metrics, "expected_entry_found_rate") >= 85:
                strengths.append("Retrieval покрывает большинство ожидаемых entry.")
        else:
            if _metric_float(metrics, "answer_supported_rate") >= 85:
                strengths.append("Ответы в основном опираются на найденные данные.")

            if _metric_int(metrics, "high_hallucination_risk") == 0:
                strengths.append("Не обнаружено ответов с высоким риском галлюцинации.")

        return strengths or [
            "Сильные стороны пока не подтверждены автоматической проверкой."
        ]

    def _problems(self, results: list[RagEvalResult], metrics: JsonObject) -> list[str]:
        problems: list[str] = []

        if _metric_float(metrics, "top3_rate") < 75:
            problems.append("Слабое попадание ожидаемых chunks в top-3 retrieval.")

        wrong_top1 = _metric_int(metrics, "wrong_entry_top1")
        if wrong_top1:
            problems.append(
                f"{wrong_top1} вопросов получили неправильный chunk на первом месте."
            )

        if not _all_retrieval_eval(results):
            high_risk = _metric_int(metrics, "high_hallucination_risk")
            if high_risk:
                problems.append(f"{high_risk} ответов имеют высокий риск галлюцинации.")

            unsupported = [result for result in results if not result.answer_supported]
            if unsupported:
                problems.append(
                    f"{len(unsupported)} ответов не подтверждены retrieved evidence."
                )
        else:
            not_found = sum(
                1
                for result in results
                if result.question.expected_entry_ids
                and not result.expected_entry_found
            )
            if not_found:
                problems.append(
                    f"{not_found} вопросов не нашли ожидаемый knowledge entry."
                )

        return problems or ["Критичных проблем автоматическая проверка не нашла."]

    def _recommendations(
        self, results: list[RagEvalResult], metrics: JsonObject
    ) -> list[str]:
        recommendations: list[str] = []

        if _metric_float(metrics, "top3_rate") < 75:
            recommendations.append(
                "Усилить retrieval: проверить entry compilation, embedding_text и hybrid search."
            )

        if _metric_int(metrics, "wrong_entry_top1"):
            recommendations.append(
                "Разделить похожие темы в базе знаний или добавить более явные заголовки/FAQ."
            )

        if not _all_retrieval_eval(results) and _metric_int(
            metrics, "high_hallucination_risk"
        ):
            recommendations.append(
                "Усилить no-answer policy: при отсутствии evidence бот должен честно говорить, что информации нет."
            )

        if any(
            result.question.question_type == "unknown"
            and result.should_answer_passed is False
            for result in results
        ):
            recommendations.append(
                "Добавить правила отказа для вопросов вне документа."
            )

        return recommendations or [
            "Поддерживать eval-набор как regression suite после каждого изменения базы знаний."
        ]

    def _markdown(
        self,
        *,
        run: RagEvalRun,
        score: float,
        readiness: str,
        strengths: list[str],
        problems: list[str],
        recommendations: list[str],
        metrics: JsonObject,
    ) -> str:
        lines = [
            "# RAG Quality Report",
            "",
            f"- Document: `{run.document_id}`",
            f"- Dataset: `{run.dataset_id}`",
            f"- Run: `{run.id}`",
            f"- Quality score: **{score:.2f}/100**",
            f"- Status: **{readiness}**",
            "",
            "## Сильные стороны",
            "",
            *[f"- {item}" for item in strengths],
            "",
            "## Проблемы",
            "",
            *[f"- {item}" for item in problems],
            "",
            "## Рекомендации",
            "",
            *[
                f"{index}. {item}"
                for index, item in enumerate(recommendations, start=1)
            ],
            "",
            "## Метрики",
            "",
        ]

        for key, value in metrics.items():
            lines.append(f"- {key}: `{value}`")

        return "\n".join(lines) + "\n"
