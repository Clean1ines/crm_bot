from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


AI_PLAYGROUND_DEFAULT_MODEL = "llama-3.1-8b-instant"

# User-provided Groq developer-plan limits. Values are input TPM limits used by
# Playground preflight validation, not billing or exact tokenizer accounting.
AI_PLAYGROUND_MODEL_LIMITS: dict[str, dict[str, int]] = {
    "canopylabs/orpheus-arabic-saudi": {
        "rpm": 10,
        "rpd": 100,
        "tpm": 1200,
        "tpd": 3600,
    },
    "canopylabs/orpheus-v1-english": {"rpm": 10, "rpd": 100, "tpm": 1200, "tpd": 3600},
    "groq/compound": {"rpm": 30, "rpd": 250, "tpm": 70000},
    "groq/compound-mini": {"rpm": 30, "rpd": 250, "tpm": 70000},
    "llama-3.1-8b-instant": {"rpm": 30, "rpd": 14400, "tpm": 6000, "tpd": 500000},
    "llama-3.3-70b-versatile": {"rpm": 30, "rpd": 1000, "tpm": 12000, "tpd": 100000},
    "meta-llama/llama-4-scout-17b-16e-instruct": {
        "rpm": 30,
        "rpd": 1000,
        "tpm": 30000,
        "tpd": 500000,
    },
    "meta-llama/llama-prompt-guard-2-22m": {
        "rpm": 30,
        "rpd": 14400,
        "tpm": 15000,
        "tpd": 500000,
    },
    "meta-llama/llama-prompt-guard-2-86m": {
        "rpm": 30,
        "rpd": 14400,
        "tpm": 15000,
        "tpd": 500000,
    },
    "openai/gpt-oss-120b": {"rpm": 30, "rpd": 1000, "tpm": 8000, "tpd": 200000},
    "openai/gpt-oss-20b": {"rpm": 30, "rpd": 1000, "tpm": 8000, "tpd": 200000},
    "openai/gpt-oss-safeguard-20b": {
        "rpm": 30,
        "rpd": 1000,
        "tpm": 8000,
        "tpd": 200000,
    },
    "qwen/qwen3-32b": {"rpm": 60, "rpd": 1000, "tpm": 6000, "tpd": 500000},
}


AiPlaygroundResponseFormat = Literal["text", "json"]
AiPlaygroundReasoningEffort = Literal["none"]
AiPlaygroundReasoningFormat = Literal["hidden", "parsed"]


class AiPlaygroundRunRequest(BaseModel):
    system_prompt: str = Field(..., min_length=1)
    user_input: str = Field(..., min_length=1)
    model: str = Field(default=AI_PLAYGROUND_DEFAULT_MODEL)
    response_format: AiPlaygroundResponseFormat = "text"
    reasoning_effort: AiPlaygroundReasoningEffort | None = None
    reasoning_format: AiPlaygroundReasoningFormat | None = None
    max_completion_tokens: int | None = Field(default=None, ge=1)


class AiPlaygroundUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class AiPlaygroundRunResponse(BaseModel):
    ok: bool = True
    model: str
    provider: str
    status: str
    raw_text: str
    parsed_json: object | None = None
    json_parse_error: str | None = None
    usage: AiPlaygroundUsage | None = None
    duration_ms: int
