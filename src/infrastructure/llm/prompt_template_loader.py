from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.application.ports.prompt_template_port import PromptTemplateNotFoundError


@dataclass(frozen=True, slots=True)
class FilePromptTemplateLoader:
    prompts_dir: Path
    fallback_language: str = "ru"

    def load(self, stem: str, *, language: str | None = None) -> str:
        candidates = self._candidate_paths(stem, language=language)
        for path in candidates:
            if path.is_file():
                return path.read_text(encoding="utf-8")
        names = ", ".join(str(path) for path in candidates)
        raise PromptTemplateNotFoundError(f"Prompt template not found: {names}")

    def load_filename(self, filename: str) -> str:
        path = self.prompts_dir / filename
        if path.is_file():
            return path.read_text(encoding="utf-8")
        raise PromptTemplateNotFoundError(f"Prompt template not found: {path}")

    def _candidate_paths(self, stem: str, *, language: str | None) -> tuple[Path, ...]:
        language = _normalize_language(language)
        fallback = _normalize_language(self.fallback_language)
        paths: list[Path] = []
        if language:
            paths.append(self.prompts_dir / f"{stem}.{language}.txt")
        if fallback and fallback != language:
            paths.append(self.prompts_dir / f"{stem}.{fallback}.txt")
        paths.append(self.prompts_dir / f"{stem}.txt")
        return tuple(dict.fromkeys(paths))


def _normalize_language(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"ru", "en", "de", "es"} else None
