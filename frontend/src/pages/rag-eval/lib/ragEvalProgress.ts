import { getErrorMessage } from '@shared/api/core/errors';
import { t } from '@shared/i18n';
import type { RagEvalProgressPayload } from '@shared/api/modules/ragEval';

export const formatNumber = (value: number): string => new Intl.NumberFormat('ru-RU').format(value);

export const formatDurationMs = (durationMs: number): string => {
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}ч ${minutes}м`;
  if (minutes > 0) return `${minutes}м ${seconds}с`;
  return `${seconds}с`;
};

export const stageLabel = (stage: string): string => {
  if (stage === 'queued') return t('ragEval.stage.queued');
  if (stage === 'started') return t('ragEval.stage.started');
  if (stage === 'dataset_generation') return t('ragEval.stage.datasetGeneration');
  if (stage === 'retrieval_checks' || stage === 'fragment_review_streaming') return t('ragEval.stage.retrievalChecks');
  if (stage === 'answer_generation') return t('ragEval.stage.answerGeneration');
  if (stage === 'running') return t('ragEval.stage.running');
  if (stage === 'completed' || stage === 'done') return t('ragEval.stage.completed');
  if (stage === 'cancelled') return t('ragEval.stage.cancelled');
  if (stage === 'paused') return t('ragEval.stage.paused');
  if (stage === 'failed') return t('ragEval.stage.failed');
  return stage || t('ragEval.stage.waiting');
};

export const statusLabel = (status: string): string => {
  if (status === 'pending') return t('ragEval.status.pending');
  if (status === 'processing' || status === 'running') return t('ragEval.status.running');
  if (status === 'paused') return t('ragEval.stage.paused');
  if (status === 'completed' || status === 'done' || status === 'succeeded' || status === 'success') return t('ragEval.stage.completed');
  if (status === 'cancelled') return t('ragEval.stage.cancelled');
  if (status === 'failed') return t('ragEval.stage.failed');
  return status || t('ragEval.stage.waiting');
};

export const progressMessage = (progress: RagEvalProgressPayload, stage: string): string => {
  const rawMessage = typeof progress.message === 'string' ? progress.message : '';
  if (stage === 'dataset_generation') return t('ragEval.stageDescription.datasetGeneration');
  if (stage === 'retrieval_checks' || stage === 'fragment_review_streaming') return t('ragEval.stageDescription.retrievalChecks');
  if (stage === 'answer_generation') return t('ragEval.stageDescription.answerGeneration');
  if (stage === 'paused') return t('ragEval.stageDescription.paused');
  if (stage === 'cancelled') return t('ragEval.stageDescription.cancelled');
  if (stage === 'failed') return getErrorMessage(rawMessage, t('ragEval.stageDescription.failed'));
  if (stage === 'completed' || stage === 'done') return t('ragEval.stageDescription.completed');
  return rawMessage || t('ragEval.stageDescription.running');
};
