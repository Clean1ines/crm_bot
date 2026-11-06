import { authedJsonRequest } from '../core/http';

export type AiPlaygroundResponseFormat = 'text' | 'json';
export type AiPlaygroundReasoningEffort = 'low' | 'medium' | 'high';

export type AiPlaygroundModelOption = {
  id: string;
  label: string;
  model?: string;
  rpm: number;
  rpd: number;
  tpm: number;
  tpd?: number;
  reasoning_effort?: AiPlaygroundReasoningEffort;
};

export const AI_PLAYGROUND_DEFAULT_MODEL = 'openai/gpt-oss-120b';

export const AI_PLAYGROUND_MODELS: AiPlaygroundModelOption[] = [
  { id: 'openai/gpt-oss-120b', label: 'openai/gpt-oss-120b', rpm: 30, rpd: 1000, tpm: 8000, tpd: 200000 },
  { id: 'openai/gpt-oss-20b', label: 'openai/gpt-oss-20b', rpm: 30, rpd: 1000, tpm: 8000, tpd: 200000 },
];

export type AiPlaygroundRunRequest = {
  system_prompt: string;
  user_input: string;
  model: string;
  response_format: AiPlaygroundResponseFormat;
  reasoning_effort?: AiPlaygroundReasoningEffort | null;
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
