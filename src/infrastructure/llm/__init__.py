from __future__ import annotations

from src.infrastructure.llm import (
    faq_workbench_claim_observations_generator as _claim_obs,
)
from src.infrastructure.llm.faq_claim_obs_contract import FaqClaimObsContractGenerator

setattr(
    _claim_obs, "FaqWorkbenchClaimObservationsGenerator", FaqClaimObsContractGenerator
)
