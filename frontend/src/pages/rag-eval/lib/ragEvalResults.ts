import { t } from '@shared/i18n';
import {
  isRagEvalProposedActionType,
  type RagEvalActionableResult,
  type RagEvalProposedActionType,
  type RagEvalResultSummary,
} from '@shared/api/modules/ragEval';

export const parseJsonValue = (value: unknown): unknown => {
  if (typeof value !== 'string') return value;
  const trimmed = value.trim();
  if (!trimmed) return value;
  try {
    return JSON.parse(trimmed) as unknown;
  } catch {
    return value;
  }
};

const getRecord = (value: unknown): Record<string, unknown> => (
  value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
);

const asNumber = (value: unknown, fallback = 0): number => (
  typeof value === 'number' && Number.isFinite(value) ? value : fallback
);

export const asStringList = (value: unknown): string[] => {
  const parsed = parseJsonValue(value);
  if (Array.isArray(parsed)) return parsed.map((item) => String(item).trim()).filter(Boolean);
  if (typeof parsed === 'string' && parsed.trim()) return [parsed.trim()];
  return [];
};

const asBoolean = (value: unknown, fallback = false): boolean => (
  typeof value === 'boolean' ? value : fallback
);

const assertNeverActionType = (value: never): never => {
  throw new Error(`Unhandled RAG eval proposed action type: ${value}`);
};

export const getEvalResults = (value: unknown): RagEvalResultSummary[] => (
  Array.isArray(value) ? value as RagEvalResultSummary[] : []
);

export const getActionableResults = (report: Record<string, unknown>): RagEvalActionableResult[] => {
  const parsed = parseJsonValue(report.actionable_results);
  if (!Array.isArray(parsed)) return [];

  return parsed
    .map((raw): RagEvalActionableResult | null => {
      const item = getRecord(raw);
      const resultId = String(item.result_id || '').trim();
      if (!resultId) return null;

      const rawActions = parseJsonValue(item.proposed_actions);
      const proposedActions = Array.isArray(rawActions)
        ? rawActions.map((rawAction) => {
          const action = getRecord(rawAction);
          const actionType = String(action.action_type || '').trim();
          if (!isRagEvalProposedActionType(actionType)) return null;
          return {
            action_type: actionType,
            target_entry_id: String(action.target_entry_id || '').trim() || null,
            reason: String(action.reason || '').trim(),
            payload: getRecord(action.payload),
          };
        }).filter((action): action is NonNullable<typeof action> => action !== null)
        : [];

      const classification = getRecord(item.classification);

      return {
        result_id: resultId,
        run_id: String(item.run_id || '').trim(),
        question_id: String(item.question_id || '').trim(),
        question: String(item.question || '').trim(),
        question_type: String(item.question_type || '').trim(),
        expected_entry_ids: asStringList(item.expected_entry_ids),
        retrieved_entry_ids: asStringList(item.retrieved_entry_ids),
        score: asNumber(item.score),
        answer_supported: asBoolean(item.answer_supported),
        wrong_entry_top1: asBoolean(item.wrong_entry_top1),
        hallucination_risk: String(item.hallucination_risk || '').trim(),
        should_answer_passed: asBoolean(item.should_answer_passed),
        classification: Object.keys(classification).length ? classification : null,
        proposed_actions: proposedActions,
      };
    })
    .filter((item): item is RagEvalActionableResult => item !== null);
};

export const actionTypeLabel = (value: RagEvalProposedActionType): string => {
  switch (value) {
    case 'attach_question_to_entry': return t('ragEval.actionType.attachQuestionToEntry');
    case 'rebuild_embedding': return t('ragEval.actionType.rebuildEntryEmbedding');
    case 'rerun_eval': return t('ragEval.actionType.rerunEval');
    case 'create_entry_from_failure': return t('ragEval.actionType.createEntryFromFailure');
  }
  return assertNeverActionType(value);
};

export const actionTypeDescription = (value: RagEvalProposedActionType): string => {
  switch (value) {
    case 'attach_question_to_entry': return t('ragEval.actionDescription.attachQuestionToEntry');
    case 'rebuild_embedding': return t('ragEval.actionDescription.rebuildEntryEmbedding');
    case 'rerun_eval': return t('ragEval.actionDescription.rerunEval');
    case 'create_entry_from_failure': return t('ragEval.actionDescription.createEntryFromFailure');
  }
  return assertNeverActionType(value);
};

export const formatResultScore = (score: number): string => `${Math.round((score > 1 ? score : score * 100))}%`;

export const riskLabel = (value: string): string => {
  if (value === 'high') return t('ragEval.risk.high');
  if (value === 'medium') return t('ragEval.risk.medium');
  if (value === 'low') return t('ragEval.risk.low');
  return t('ragEval.risk.unknown');
};

export const resultProblemLabel = (result: RagEvalActionableResult): string => {
  if (result.wrong_entry_top1 && !result.answer_supported) return t('ragEval.problem.wrongEntryAndUnsupported');
  if (result.wrong_entry_top1) return t('ragEval.problem.wrongEntryTop1');
  if (!result.answer_supported) return t('ragEval.problem.unsupportedAnswer');
  if (result.hallucination_risk === 'high') return t('ragEval.problem.highHallucinationRisk');
  if (!result.should_answer_passed) return t('ragEval.problem.shouldAnswerFailed');
  return t('ragEval.problem.fallback');
};

export const readinessLabel = (value: unknown): string => {
  const readiness = String(value || '').trim();
  if (readiness === 'ready') return t('ragEval.readiness.ready');
  if (readiness === 'needs_review') return t('ragEval.readiness.needsReview');
  if (readiness === 'not_ready') return t('ragEval.readiness.notReady');
  return readiness || t('ragEval.readiness.noStatus');
};
