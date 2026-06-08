from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TokenPrice:
    input_per_million: Decimal | None = None
    output_per_million: Decimal | None = None

    def __post_init__(self) -> None:
        if self.input_per_million is not None and self.input_per_million < 0:
            raise ValueError("TokenPrice.input_per_million must be >= 0 when provided")
        if self.output_per_million is not None and self.output_per_million < 0:
            raise ValueError("TokenPrice.output_per_million must be >= 0 when provided")

    @classmethod
    def unknown(cls) -> "TokenPrice":
        return cls()
