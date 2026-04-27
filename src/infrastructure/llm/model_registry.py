"""
Model registry for managing available LLM models and their capabilities.
Loads model definitions from a YAML configuration file.
"""

import yaml
from pathlib import Path
from collections.abc import Mapping

from src.infrastructure.logging.logger import get_logger
from src.infrastructure.config.settings import settings

logger = get_logger(__name__)


def _as_text(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


def _as_int(value: object, default: int = 999) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return default
        try:
            return int(normalized)
        except ValueError:
            return default
    return default


def _capability_enabled(model: Mapping[str, object], capability: str) -> bool:
    raw_capabilities = model.get("capabilities")
    if not isinstance(raw_capabilities, Mapping):
        return False
    return bool(raw_capabilities.get(capability))


def _model_priority(model: Mapping[str, object]) -> int:
    return _as_int(model.get("priority"), 999)


class ModelRegistry:
    """
    Registry of available models with their static limits and capabilities.
    Data is loaded from a YAML file specified in settings.MODEL_CONFIG_PATH.
    """

    def __init__(self):
        self._models: dict[str, dict[str, object]] = {}
        self._load_models()

    def _load_models(self) -> None:
        """Load model definitions from YAML file."""
        config_path = Path(settings.MODEL_CONFIG_PATH)
        if not config_path.exists():
            logger.warning(
                f"Model config file not found at {config_path}, using built-in defaults"
            )
            self._load_defaults()
            return

        try:
            with open(config_path, "r") as f:
                data = yaml.safe_load(f)
            models_list = data.get("models", [])
            for model in models_list:
                model_id = model.get("id")
                if model_id:
                    self._models[model_id] = model
                else:
                    logger.warning(
                        "Skipping model entry without id", extra={"model": model}
                    )
            logger.info(f"Loaded {len(self._models)} models from {config_path}")
        except Exception:
            logger.exception(
                "Failed to load model config", extra={"path": str(config_path)}
            )
            self._load_defaults()

    def _load_defaults(self) -> None:
        """Fallback to built‑in default models (based on Groq's developer plan)."""
        defaults = [
            {
                "id": "llama-3.3-70b-versatile",
                "provider": "groq",
                "priority": 1,
                "limits": {"tpd": 100000, "tpm": 12000, "rpd": 1000, "rpm": 30},
                "capabilities": {"complex": True},
            },
            {
                "id": "llama-3.1-8b-instant",
                "provider": "groq",
                "priority": 2,
                "limits": {"tpd": 500000, "tpm": 6000, "rpd": 14400, "rpm": 30},
                "capabilities": {"complex": False},
            },
            {
                "id": "qwen/qwen3-32b",
                "provider": "groq",
                "priority": 3,
                "limits": {"tpd": 500000, "tpm": 6000, "rpd": 1000, "rpm": 60},
                "capabilities": {"complex": True},
            },
            # Add more models as needed
        ]
        for model in defaults:
            model_id = _as_text(model.get("id"))
            if model_id:
                self._models[model_id] = model
        logger.info(f"Loaded {len(self._models)} default models")

    def get_all_models(self) -> list[dict[str, object]]:
        """Return list of all registered models."""
        return list(self._models.values())

    def get_model(self, model_id: str) -> dict[str, object] | None:
        """Return model definition by ID, or None if not found."""
        return self._models.get(model_id)

    def get_models_by_capability(
        self, complex_needed: bool = False
    ) -> list[dict[str, object]]:
        """
        Return models that match the required capability.
        If complex_needed is True, only models with complex=True are returned.
        Otherwise, all models are considered.
        """
        models = list(self._models.values())
        if complex_needed:
            models = [m for m in models if _capability_enabled(m, "complex")]
        return models

    def get_models_sorted_by_priority(
        self, complex_needed: bool = False
    ) -> list[dict[str, object]]:
        """Return models sorted by priority (lower number = higher priority)."""
        models = self.get_models_by_capability(complex_needed)
        return sorted(models, key=_model_priority)
