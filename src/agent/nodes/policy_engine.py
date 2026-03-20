"""
Policy engine node for LangGraph pipeline.

Implements business logic to determine next action based on extracted intent,
lifecycle stage, and other context. Uses a pure Python rule engine.
"""

from typing import Dict, Any, Optional
from src.core.logging import get_logger, log_node_execution
from src.agent.state import AgentState

logger = get_logger(__name__)


# Transition rules table
# Format: (current_lifecycle, intent) -> (new_lifecycle, decision, cta)
TRANSITIONS = {
    # Cold prospects
    ("cold", "pricing"): ("interested", "LLM_GENERATE", "request_demo"),
    ("cold", "sales"): ("interested", "LLM_GENERATE", "request_demo"),
    ("cold", "support"): ("cold", "LLM_GENERATE", "none"),  # Keep cold for support
    ("cold", "feedback"): ("cold", "LLM_GENERATE", "none"),
    ("cold", "other"): ("cold", "LLM_GENERATE", "none"),

    # Interested prospects
    ("interested", "pricing"): ("warm", "CALL_TOOL", "book_consultation"),
    ("interested", "sales"): ("warm", "CALL_TOOL", "book_consultation"),
    ("interested", "support"): ("interested", "LLM_GENERATE", "none"),
    ("interested", "feedback"): ("interested", "LLM_GENERATE", "none"),
    ("interested", "other"): ("interested", "LLM_GENERATE", "none"),

    # Warm leads
    ("warm", "pricing"): ("hot", "CALL_TOOL", "call_manager"),
    ("warm", "sales"): ("hot", "CALL_TOOL", "call_manager"),
    ("warm", "support"): ("warm", "ESCALATE_TO_HUMAN", "call_manager"),
    ("warm", "feedback"): ("warm", "LLM_GENERATE", "none"),
    ("warm", "other"): ("warm", "LLM_GENERATE", "none"),

    # Hot leads
    ("hot", "pricing"): ("hot", "ESCALATE_TO_HUMAN", "call_manager"),
    ("hot", "sales"): ("hot", "ESCALATE_TO_HUMAN", "call_manager"),
    ("hot", "support"): ("hot", "ESCALATE_TO_HUMAN", "call_manager"),
    ("hot", "feedback"): ("hot", "LLM_GENERATE", "none"),
    ("hot", "other"): ("hot", "LLM_GENERATE", "none"),

    # Default fallback
    (None, None): (None, "LLM_GENERATE", "none"),
}

# Default values
DEFAULT_LIFECYCLE = "cold"
DEFAULT_DECISION = "LLM_GENERATE"
DEFAULT_CTA = "none"


def get_decision(
    lifecycle: Optional[str],
    intent: Optional[str],
    features: Optional[Dict] = None
) -> tuple[str, str, str]:
    """
    Determine decision, new lifecycle, and cta based on current state.

    Args:
        lifecycle: Current lifecycle stage (cold, interested, warm, hot).
        intent: Detected intent from intent extractor.
        features: Extracted features (may influence decision).

    Returns:
        Tuple of (new_lifecycle, decision, cta).
    """
    # Normalize inputs
    if lifecycle not in ["cold", "interested", "warm", "hot"]:
        lifecycle = DEFAULT_LIFECYCLE
    if intent not in ["pricing", "sales", "support", "feedback", "other"]:
        intent = "other"

    # Look up transition
    transition = TRANSITIONS.get((lifecycle, intent))
    if not transition:
        transition = TRANSITIONS.get((lifecycle, None), TRANSITIONS.get((None, None)))

    new_lifecycle, decision, cta = transition

    # Override decision if certain high-value features are mentioned
    if features and isinstance(features, dict):
        if any(score > 0.7 for score in features.values()):
            # High interest in any feature -> escalate
            if decision != "ESCALATE_TO_HUMAN":
                decision = "ESCALATE_TO_HUMAN"
                cta = "call_manager"
                logger.debug("High feature interest triggered escalation")

    return new_lifecycle, decision, cta


def create_policy_engine_node():
    """
    Factory function that creates a policy engine node.

    The policy engine is a pure Python function (no LLM) that uses a rule table
    to decide next action based on intent and lifecycle.

    Returns:
        An async function that takes an AgentState dict and returns a dict
        with updates to the state (decision, lifecycle, cta).
    """
    async def _policy_engine_node_impl(state: AgentState) -> Dict[str, Any]:
        """
        Apply business rules to decide next action.

        Expected state fields:
          - lifecycle: Optional[str] (current stage)
          - intent: Optional[str] (extracted intent)
          - features: Optional[Dict] (extracted features)

        Actions:
          1. Determine new lifecycle, decision, and cta using get_decision.
          2. Return updates to state.

        Returns:
            Dict with decision, lifecycle (new), cta.
        """
        lifecycle = state.get("lifecycle") or DEFAULT_LIFECYCLE
        intent = state.get("intent")
        features = state.get("features")

        new_lifecycle, decision, cta = get_decision(lifecycle, intent, features)

        logger.debug(
            "Policy decision",
            extra={
                "old_lifecycle": lifecycle,
                "new_lifecycle": new_lifecycle,
                "intent": intent,
                "decision": decision,
                "cta": cta
            }
        )

        result = {
            "decision": decision,
            "cta": cta,
            "lifecycle": new_lifecycle
        }
        # Only include if changed to avoid overwriting with same value
        if new_lifecycle == lifecycle:
            result.pop("lifecycle")

        return result

    def _get_policy_input_size(state: AgentState) -> int:
        # Safely compute length of features and intent
        return len(str(state.get("features") or "")) + len(str(state.get("intent") or ""))

    def _get_policy_output_size(result: Dict[str, Any]) -> int:
        return 1  # decision is the main output

    async def policy_engine_node(state: AgentState) -> Dict[str, Any]:
        return await log_node_execution(
            "policy_engine",
            _policy_engine_node_impl,
            state,
            get_input_size=_get_policy_input_size,
            get_output_size=_get_policy_output_size
        )

    return policy_engine_node
