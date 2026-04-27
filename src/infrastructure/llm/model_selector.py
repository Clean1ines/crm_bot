"""
Model selector: chooses the best available model based on current rate limits and task complexity.
"""


from src.infrastructure.logging.logger import get_logger
from src.infrastructure.llm.model_registry import ModelRegistry
from src.infrastructure.llm.rate_limit_tracker import RateLimitTracker
from src.infrastructure.config.settings import settings

logger = get_logger(__name__)


class ModelSelector:
    """
    Selects an appropriate model considering remaining rate limits and required capabilities.
    """
    
    def __init__(self, registry: ModelRegistry, tracker: RateLimitTracker):
        self.registry = registry
        self.tracker = tracker
    
    async def get_best_model(self, complex_needed: bool = False) -> str:
        """
        Return the ID of the best available model.
        Strategy: iterate models in priority order (lowest priority number first),
        check if they have remaining tokens (TPD) > 0 (or above a threshold).
        If none have tokens, return the default model.
        """
        models = self.registry.get_models_sorted_by_priority(complex_needed)
        if not models:
            logger.warning("No models match capabilities, using default")
            return settings.DEFAULT_MODEL
        
        for model in models:
            model_id = model["id"]
            remaining = await self.tracker.get_remaining(model_id)
            # Check tokens_remaining – if it's present and > 0, use it.
            # The header x-ratelimit-remaining-tokens refers to TPM (per minute).
            # For TPD we don't get from headers, but we can infer from limits.
            # For simplicity, if we have a token remaining value (even per minute), assume available.
            # A more sophisticated check could involve the static TPD limit and an estimate.
            tokens_rem_str = remaining.get("tokens_remaining")
            if tokens_rem_str is not None:
                try:
                    tokens_rem = int(tokens_rem_str)
                    if tokens_rem > 100:  # arbitrary small threshold
                        logger.debug("Selected model", extra={"model": model_id, "tokens_remaining": tokens_rem})
                        return model_id
                except ValueError:
                    pass
            # If no token info, assume available (fallback)
            logger.debug("Model has no token info, assuming available", extra={"model": model_id})
            return model_id
        
        # If all models have zero tokens, return default
        logger.warning("All models appear rate-limited, using default")
        return settings.DEFAULT_MODEL
