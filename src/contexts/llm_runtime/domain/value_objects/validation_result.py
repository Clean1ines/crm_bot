from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LlmValidationResult:
    is_valid: bool
    error_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.is_valid and self.error_codes:
            raise ValueError("Valid result must not carry error_codes")
        if not self.is_valid and not self.error_codes:
            raise ValueError("Invalid result must carry at least one error code")
        for error_code in self.error_codes:
            if not error_code or not error_code.strip():
                raise ValueError("Validation error code must be non-empty")

    @classmethod
    def valid(cls) -> "LlmValidationResult":
        return cls(is_valid=True)

    @classmethod
    def invalid(cls, *error_codes: str) -> "LlmValidationResult":
        return cls(is_valid=False, error_codes=tuple(error_codes))
