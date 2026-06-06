import { authedJsonRequest } from '../core/http';

export type AiPlaygroundResponseFormat = 'text' | 'json';

export type AiPlaygroundModelOption = {
  id: string;
  label: string;
  rpm: number;
  rpd: number;
  tpm: number;
  tpd?: number;
};

export const AI_PLAYGROUND_DEFAULT_MODEL = 'llama-3.1-8b-instant';

export const AI_PLAYGROUND_MODELS: AiPlaygroundModelOption[] = [
  { id: 'llama-3.1-8b-instant', label: 'llama-3.1-8b-instant', rpm: 30, rpd: 14400, tpm: 6000, tpd: 500000 },
  { id: 'qwen/qwen3-32b', label: 'qwen/qwen3-32b', rpm: 60, rpd: 1000, tpm: 6000, tpd: 500000 },
  { id: 'llama-3.3-70b-versatile', label: 'llama-3.3-70b-versatile', rpm: 30, rpd: 1000, tpm: 12000, tpd: 100000 },
  { id: 'meta-llama/llama-4-scout-17b-16e-instruct', label: 'meta-llama/llama-4-scout-17b-16e-instruct', rpm: 30, rpd: 1000, tpm: 30000, tpd: 500000 },
  { id: 'openai/gpt-oss-120b', label: 'openai/gpt-oss-120b', rpm: 30, rpd: 1000, tpm: 8000, tpd: 200000 },
  { id: 'openai/gpt-oss-20b', label: 'openai/gpt-oss-20b', rpm: 30, rpd: 1000, tpm: 8000, tpd: 200000 },
  { id: 'groq/compound', label: 'groq/compound', rpm: 30, rpd: 250, tpm: 70000 },
  { id: 'groq/compound-mini', label: 'groq/compound-mini', rpm: 30, rpd: 250, tpm: 70000 },
];

export type AiPlaygroundRunRequest = {
  system_prompt: string;
  user_input: string;
  model: string;
  response_format: AiPlaygroundResponseFormat;
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
