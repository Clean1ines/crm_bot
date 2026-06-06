import React, { useMemo, useState } from "react";
import { Loader2, Send } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import toast from "react-hot-toast";

import { getErrorMessage } from "@shared/api/core/errors";
import {
  AI_PLAYGROUND_DEFAULT_MODEL,
  AI_PLAYGROUND_MODELS,
  aiPlaygroundApi,
  aiPlaygroundLimitMessage,
  estimateAiPlaygroundInputTokens,
  type AiPlaygroundRunResponse,
} from "@shared/api/modules/aiPlayground";

type AiPlaygroundPanelProps = {
  projectId: string;
};

const formatNumber = (value: number): string =>
  new Intl.NumberFormat("ru-RU").format(value);

const stringifyJson = (value: unknown): string => {
  if (value === null || value === undefined) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

export const AiPlaygroundPanel: React.FC<AiPlaygroundPanelProps> = ({
  projectId,
}) => {
  const [model, setModel] = useState(AI_PLAYGROUND_DEFAULT_MODEL);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [userInput, setUserInput] = useState("");
  const [expectJson, setExpectJson] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const selectedModel = useMemo(
    () => AI_PLAYGROUND_MODELS.find((item) => item.id === model) ?? AI_PLAYGROUND_MODELS[0],
    [model],
  );

  const estimatedTokens = useMemo(
    () => estimateAiPlaygroundInputTokens(systemPrompt, userInput),
    [systemPrompt, userInput],
  );

  const exceedsTpm = estimatedTokens > selectedModel.tpm;

  const mutation = useMutation<AiPlaygroundRunResponse, unknown, void>({
    mutationFn: async () => {
      if (!projectId) throw new Error("project_id не найден");

      const { data } = await aiPlaygroundApi.run(projectId, {
        system_prompt: systemPrompt,
        user_input: userInput,
        model,
        response_format: expectJson ? "json" : "text",
      });

      return data;
    },
    onError: (error) => {
      const message = getErrorMessage(error, "Не удалось выполнить AI-запрос");
      setLocalError(message);
      toast.error(message);
    },
  });

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();

    const trimmedSystemPrompt = systemPrompt.trim();
    const trimmedUserInput = userInput.trim();

    if (!trimmedSystemPrompt) {
      const message = "Инструкция для модели не должна быть пустой";
      setLocalError(message);
      toast.error(message);
      return;
    }

    if (!trimmedUserInput) {
      const message = "Текст для проверки не должен быть пустым";
      setLocalError(message);
      toast.error(message);
      return;
    }

    if (exceedsTpm) {
      const message = aiPlaygroundLimitMessage(
        estimatedTokens,
        selectedModel.id,
        selectedModel.tpm,
      );
      setLocalError(message);
      toast.error(message);
      return;
    }

    setLocalError(null);
    mutation.mutate();
  };

  const result = mutation.data;

  return (
    <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-sm sm:p-5 lg:p-6">
      <div className="mb-5 flex flex-col gap-2">
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">
          Проверка AI-запроса
        </h2>
        <p className="text-sm leading-relaxed text-[var(--text-muted)]">
          Stateless-проверка: инструкция + пользовательский текст → сырой ответ модели.
          Ничего не сохраняется в БД, не ставится в очередь и не связано с обработкой документов.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <label className="block">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            Модель
          </span>
          <select
            value={model}
            onChange={(event) => setModel(event.target.value)}
            disabled={mutation.isPending}
            className="min-h-11 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--control-bg)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 disabled:cursor-wait disabled:opacity-60"
          >
            {AI_PLAYGROUND_MODELS.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
          <span className="mt-1 block text-xs text-[var(--text-muted)]">
            TPM: {formatNumber(selectedModel.tpm)} · примерная длина запроса:{" "}
            {formatNumber(estimatedTokens)} токенов
          </span>
        </label>

        <label className="block">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            Инструкция для модели
          </span>
          <textarea
            value={systemPrompt}
            onChange={(event) => setSystemPrompt(event.target.value)}
            placeholder="Ты извлекаешь claims из текста и возвращаешь..."
            rows={7}
            disabled={mutation.isPending}
            className="min-h-40 w-full resize-y rounded-xl bg-[var(--control-bg)] px-4 py-3 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 disabled:cursor-wait disabled:opacity-60"
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            Текст для проверки
          </span>
          <textarea
            value={userInput}
            onChange={(event) => setUserInput(event.target.value)}
            placeholder="## 1. Что это за продукт..."
            rows={8}
            disabled={mutation.isPending}
            className="min-h-48 w-full resize-y rounded-xl bg-[var(--control-bg)] px-4 py-3 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 disabled:cursor-wait disabled:opacity-60"
          />
        </label>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <label className="inline-flex items-center gap-2 text-sm text-[var(--text-primary)]">
            <input
              type="checkbox"
              checked={expectJson}
              onChange={(event) => setExpectJson(event.target.checked)}
              disabled={mutation.isPending}
              className="h-4 w-4 rounded border-[var(--border-subtle)]"
            />
            Ожидать JSON-ответ
          </label>

          <button
            type="submit"
            disabled={mutation.isPending || exceedsTpm}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-[var(--accent-primary)] px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-[var(--accent-hover)] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {mutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Отправляю...
              </>
            ) : (
              <>
                <Send className="h-4 w-4" />
                Отправить запрос
              </>
            )}
          </button>
        </div>

        {(localError || exceedsTpm) && (
          <div className="rounded-xl bg-[var(--accent-danger-bg)] p-3 text-sm text-[var(--accent-danger-text)]">
            {localError ||
              aiPlaygroundLimitMessage(estimatedTokens, selectedModel.id, selectedModel.tpm)}
          </div>
        )}
      </form>

      {result && (
        <div className="mt-6 space-y-4">
          <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
            <div className="mb-2 text-sm font-semibold text-[var(--text-primary)]">
              Результат
            </div>
            <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap rounded-lg bg-[var(--control-bg)] p-3 text-xs text-[var(--text-primary)]">
              {result.raw_text}
            </pre>
          </div>

          {expectJson && (
            <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
              <div className="mb-2 text-sm font-semibold text-[var(--text-primary)]">
                JSON
              </div>
              {result.parsed_json !== null ? (
                <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap rounded-lg bg-[var(--control-bg)] p-3 text-xs text-[var(--text-primary)]">
                  {stringifyJson(result.parsed_json)}
                </pre>
              ) : (
                <div className="rounded-lg bg-[var(--accent-warning-bg)] p-3 text-sm text-[var(--accent-warning)]">
                  {result.json_parse_error || "JSON не распарсился"}
                </div>
              )}
            </div>
          )}

          <div className="rounded-xl bg-[var(--surface-secondary)] p-4 text-sm text-[var(--text-muted)]">
            <span className="font-medium text-[var(--text-primary)]">Метрики:</span>{" "}
            {result.provider} · {result.model} · {result.status} ·{" "}
            {result.usage
              ? `${formatNumber(result.usage.total_tokens)} токенов`
              : "токены недоступны"}{" "}
            · {formatNumber(result.duration_ms)} мс
          </div>
        </div>
      )}
    </section>
  );
};
