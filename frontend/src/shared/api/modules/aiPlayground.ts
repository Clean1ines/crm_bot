import { authedJsonRequest } from '../core/http';

export type AiPlaygroundResponseFormat = 'text' | 'json';
export type AiPlaygroundReasoningEffort = 'none';
export type AiPlaygroundReasoningFormat = 'hidden' | 'parsed';

export type AiPlaygroundModelOption = {
  id: string;
  label: string;
  model?: string;
  rpm: number;
  rpd: number;
  tpm: number;
  tpd?: number;
  reasoning_effort?: AiPlaygroundReasoningEffort;
  reasoning_format?: AiPlaygroundReasoningFormat;
};

export const AI_PLAYGROUND_DEFAULT_MODEL = 'qwen/qwen3.6-27b';

export const AI_PLAYGROUND_MODELS: AiPlaygroundModelOption[] = [
  { id: 'qwen/qwen3.6-27b', label: 'qwen/qwen3.6-27b', rpm: 30, rpd: 1000, tpm: 8000, tpd: 200000 },
  {
    id: 'qwen/qwen3.6-27b:reasoning-none',
    label: 'qwen/qwen3.6-27b · reasoning off',
    model: 'qwen/qwen3.6-27b',
    rpm: 30,
    rpd: 1000,
    tpm: 8000,
    tpd: 200000,
    reasoning_effort: 'none',
  },
  { id: 'openai/gpt-oss-120b', label: 'openai/gpt-oss-120b', rpm: 30, rpd: 1000, tpm: 8000, tpd: 200000 },
  { id: 'openai/gpt-oss-20b', label: 'openai/gpt-oss-20b', rpm: 30, rpd: 1000, tpm: 8000, tpd: 200000 },
  { id: 'openai/gpt-oss-safeguard-20b', label: 'openai/gpt-oss-safeguard-20b', rpm: 30, rpd: 1000, tpm: 8000, tpd: 200000 },
  { id: 'meta-llama/llama-prompt-guard-2-22m', label: 'meta-llama/llama-prompt-guard-2-22m', rpm: 30, rpd: 14400, tpm: 15000, tpd: 500000 },
  { id: 'meta-llama/llama-prompt-guard-2-86m', label: 'meta-llama/llama-prompt-guard-2-86m', rpm: 30, rpd: 14400, tpm: 15000, tpd: 500000 },
  { id: 'groq/compound', label: 'groq/compound', rpm: 30, rpd: 250, tpm: 70000 },
  { id: 'groq/compound-mini', label: 'groq/compound-mini', rpm: 30, rpd: 250, tpm: 70000 },
  { id: 'canopylabs/orpheus-arabic-saudi', label: 'canopylabs/orpheus-arabic-saudi', rpm: 10, rpd: 100, tpm: 1200, tpd: 3600 },
  { id: 'canopylabs/orpheus-v1-english', label: 'canopylabs/orpheus-v1-english', rpm: 10, rpd: 100, tpm: 1200, tpd: 3600 },
];

export type AiPlaygroundRunRequest = {
  system_prompt: string;
  user_input: string;
  model: string;
  response_format: AiPlaygroundResponseFormat;
  reasoning_effort?: AiPlaygroundReasoningEffort | null;
  reasoning_format?: AiPlaygroundReasoningFormat | null;
};

export type AiPlaygroundUsage = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
};

export type AiPlaygroundRunResponse = {
  ok: boolean;
  model: string;
  provider: string;
  status: string;
  raw_text: string;
  parsed_json: unknown | null;
  json_parse_error: string | null;
  usage: AiPlaygroundUsage | null;
  duration_ms: number;
};

export const estimateAiPlaygroundInputTokens = (
  systemPrompt: string,
  userInput: string,
): number => Math.max(1, Math.ceil(`${systemPrompt}\n\n${userInput}`.length / 4));

export const aiPlaygroundLimitMessage = (
  tokenCount: number,
  model: string,
  tpm: number,
): string => `Твоё сообщение: ${tokenCount} токенов. Лимит для ${model}: ${tpm} TPM.`;

export const aiPlaygroundApi = {
  run: (projectId: string, payload: AiPlaygroundRunRequest) =>
    authedJsonRequest<AiPlaygroundRunResponse, AiPlaygroundRunRequest>(
      `/api/projects/${projectId}/ai-playground/run`,
      {
        method: 'POST',
        body: payload,
      },
    ),
};
