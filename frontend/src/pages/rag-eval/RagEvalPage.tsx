import { t } from '@shared/i18n';
import React, { useMemo, useState } from 'react';
import {
  FileText,
  Loader2,
  Play,
  ShieldCheck,
  XCircle,
  BarChart3,
} from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';

import {
  type RagEvalReviewGroup,
  type RagEvalReviewQuestion,
  ragEvalApi,
  type KnowledgeEditActionExecutionSummary,
  type RagEvalDocumentStatusResponse,
  type RagEvalFullRunAcceptedResponse,
} from '@shared/api/modules/ragEval';
import { KnowledgeCurationConsole } from './components/KnowledgeCurationConsole';
import { ActionableResultsPanel } from './components/RagEvalMainPanels';
import { ApplyAcceptedQuestionsPanel, TechnicalDiagnosticsDisclosure } from './components/RagEvalWorkflowPanels';
import { RagEvalResultsPanel, ReportSummaryCard } from './components/RagEvalSummaryPanels';
import { DocumentEvalOverviewCard, EvalProblemMap } from './components/RagEvalReviewOverview';
import { EvalFiltersBar, FragmentReviewCard, JobProgressCard, QuestionReviewDrawer } from './components/RagEvalReviewRuntimeSections';
import { useRagEvalDocuments } from './hooks/useRagEvalDocuments';
import { useRagEvalReview } from './hooks/useRagEvalReview';
import { useRagEvalJobs } from './hooks/useRagEvalJobs';
import { useRagEvalMutations } from './hooks/useRagEvalMutations';
import { getActionableResults, getEvalResults } from './lib/ragEvalResults';
import {
  questionIsProblem,
  groupMatchesFilter,
  sortReviewGroups,
  type EvalReviewFilter,
  type EvalReviewSort,
} from './lib/ragEvalReviewFilters';
import { formatNumber, statusLabel } from './lib/ragEvalProgress';
import { getRecord } from './lib/ragEvalRuntimeUtils';
import { getJobStatus, isJobTerminal } from './lib/ragEvalStatus';
import { ReportJsonBlock } from './components/RagEvalReportComponents';

const ACTIVE_RUN_STATUSES = new Set(['created', 'pending', 'processing', 'generating', 'ready', 'running', 'paused']);










export const RagEvalPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();

  const [selectedDocumentId, setSelectedDocumentId] = useState('');
  const [lastQueued, setLastQueued] = useState<RagEvalFullRunAcceptedResponse | null>(null);
  const [lastActionExecutionSummary, setLastActionExecutionSummary] = useState<KnowledgeEditActionExecutionSummary | null>(null);
  const [reviewFilter, setReviewFilter] = useState<EvalReviewFilter>('all');
  const [reviewSort, setReviewSort] = useState<EvalReviewSort>('most_problematic');
  const [selectedReviewQuestion, setSelectedReviewQuestion] = useState<RagEvalReviewQuestion | null>(null);
  const [selectedReviewGroup, setSelectedReviewGroup] = useState<RagEvalReviewGroup | null>(null);
  const [activeReviewTab, setActiveReviewTab] = useState<'curation' | 'retrieval'>('curation');

  const { documentsQuery, processedDocuments, activeDocumentId, activeDocument } = useRagEvalDocuments(projectId, selectedDocumentId);

  const statusQuery = useQuery({
    queryKey: ['rag-eval-status', activeDocumentId],
    queryFn: async () => ragEvalApi.getStatus(activeDocumentId),
    enabled: !!activeDocumentId,
    retry: false,
    refetchInterval: (query) => {
      const data = query.state.data as RagEvalDocumentStatusResponse | undefined;
      const status = String(data?.run?.status || '');
      return ACTIVE_RUN_STATUSES.has(status) ? 5000 : false;
    },
  });

  const { reviewQuery } = useRagEvalReview(activeDocumentId, statusQuery.data?.run as Record<string, unknown> | undefined);
  const { visibleJob, progressQuery } = useRagEvalJobs(activeDocumentId, lastQueued?.job_id);

  const invalidateEvalQueries = async () => {
    await queryClient.invalidateQueries({ queryKey: ['rag-eval-status', activeDocumentId] });
    await queryClient.invalidateQueries({ queryKey: ['rag-eval-jobs', activeDocumentId] });
    await queryClient.invalidateQueries({ queryKey: ['rag-eval-job-progress'] });
    await queryClient.invalidateQueries({ queryKey: ['rag-eval-latest-review', activeDocumentId] });
  };

  const {
    runMutation,
    pauseMutation,
    resumeMutation,
    cancelMutation,
    executeActionsMutation,
    reviewQuestionMutation,
    editQuestionMutation,
    applyAcceptedMutation,
  } = useRagEvalMutations({
    activeDocumentId,
    queryClient,
    setLastQueued,
    setLastActionExecutionSummary,
    invalidateEvalQueries,
  });

  const latestReportPayload = statusQuery.data?.report ?? null;
  const latestReport = getRecord(latestReportPayload);
  const actionableResults = useMemo(() => getActionableResults(latestReport), [latestReport]);
  const latestRun = statusQuery.data?.run ?? null;
  const latestRunRecord = getRecord(latestRun);
  const latestRunResults = getEvalResults(latestRunRecord.results);
  const latestReportResults = getEvalResults(latestReport.results);
  const visibleResults = latestRunResults.length ? latestRunResults : latestReportResults;
  const progressJob = progressQuery.data?.job ?? visibleJob;
  const progressPayload = progressJob?.progress ?? visibleJob?.progress ?? (
    progressJob
      ? { percent: progressJob.percent, status: getJobStatus(progressJob) }
      : null
  );
  const review = reviewQuery.data?.review ?? null;
  const reviewGroups = useMemo(() => {
    if (!review) return [];
    return sortReviewGroups(
      review.groups.filter((group) => groupMatchesFilter(group, reviewFilter)),
      reviewSort,
    );
  }, [review, reviewFilter, reviewSort]);
  const acceptedReviewCount = useMemo(() => (
    review?.groups.reduce((total, group) => total + group.questions.filter((question) => question.review.status === 'accepted' || question.review.status === 'edited').length, 0) ?? 0
  ), [review]);
  const reviewRunId = String(review?.run.id || '');

  const isControlMutating = pauseMutation.isPending || resumeMutation.isPending || cancelMutation.isPending;
  const executingResultId = executeActionsMutation.isPending
    ? executeActionsMutation.variables ?? null
    : null;

  if (documentsQuery.isLoading) {
    return (
      <div className="p-4 text-sm text-[var(--text-muted)] sm:p-6 lg:p-8">
        {t('ragEval.documents.loading')}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6 lg:p-8">
      <div>
        <h1 className="text-2xl font-semibold leading-tight text-[var(--text-primary)] sm:text-3xl">
          {t('ragEval.page.title')}
        </h1>
        <p className="mt-2 max-w-3xl text-sm text-[var(--text-muted)]">
          {t('ragEval.page.descriptionLine1')}
          {t('ragEval.page.descriptionLine2')}
        </p>
      </div>

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
        <div className="mb-5 flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">{t('ragEval.run.title')}</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {t('ragEval.run.description')}
            </p>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-[var(--text-secondary)]">{t('ragEval.run.documentLabel')}</span>
            <select
              value={activeDocumentId}
              onChange={(event) => {
                setSelectedDocumentId(event.target.value);
                setLastActionExecutionSummary(null);
              }}
              className="w-full rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none"
            >
              {processedDocuments.map((doc) => (
                <option key={doc.id} value={doc.id}>
                  {doc.file_name} · {doc.chunk_count} {t('ragEval.document.fragments')}
                </option>
              ))}
            </select>
          </label>



          <button
            type="button"
            onClick={() => runMutation.mutate()}
            disabled={!activeDocumentId || runMutation.isPending}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--accent-primary)] px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50 lg:self-end"
          >
            {runMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {t('ragEval.run.start')}
          </button>
        </div>

        {activeDocument && (
          <div className="mt-4 flex items-center gap-2 rounded-xl bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-muted)]">
            <FileText className="h-4 w-4" />
            <span>{activeDocument.file_name}</span>
            <span>·</span>
            <span>{formatNumber(activeDocument.chunk_count)} {t('ragEval.document.fragments')}</span>
          </div>
        )}
      </section>

      <JobProgressCard
        job={progressJob ?? null}
        progress={progressPayload}
        isMutating={isControlMutating}
        onPause={() => {
          if (progressJob?.id) pauseMutation.mutate(progressJob.id);
        }}
        onResume={() => {
          if (progressJob?.id) resumeMutation.mutate(progressJob.id);
        }}
        onCancel={() => {
          if (progressJob?.id) cancelMutation.mutate(progressJob.id);
        }}
      />

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-2 shadow-[var(--shadow-card)]">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setActiveReviewTab('curation')}
            className={`rounded-xl px-4 py-2 text-sm font-semibold ${activeReviewTab === 'curation' ? 'bg-[var(--accent-primary)] text-white' : 'bg-[var(--control-bg)] text-[var(--text-muted)]'}`}
          >
            Сборка знаний / Курация знаний
          </button>
          <button
            type="button"
            onClick={() => setActiveReviewTab('retrieval')}
            className={`rounded-xl px-4 py-2 text-sm font-semibold ${activeReviewTab === 'retrieval' ? 'bg-[var(--accent-primary)] text-white' : 'bg-[var(--control-bg)] text-[var(--text-muted)]'}`}
          >
            Проверка поиска
          </button>
        </div>
      </section>

      {activeReviewTab === 'curation' ? (
        <KnowledgeCurationConsole
          projectId={String(projectId || '')}
          documentId={activeDocumentId}
          documentName={activeDocument?.file_name}
          onInvalidateRagEval={invalidateEvalQueries}
        />
      ) : reviewQuery.isLoading && !review ? (
        <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 text-sm text-[var(--text-muted)] shadow-[var(--shadow-card)]">
          <Loader2 className="mr-2 inline h-4 w-4 animate-spin" /> Загружаем review console...
        </section>
      ) : review ? (
        <>
          <DocumentEvalOverviewCard
            review={review}
            documentName={activeDocument?.file_name || String(review.run.document_id || '')}
            onShowProblems={() => setReviewFilter('problematic')}
          />
          <EvalProblemMap review={review} />
          <EvalFiltersBar
            filter={reviewFilter}
            sort={reviewSort}
            onFilterChange={setReviewFilter}
            onSortChange={setReviewSort}
          />
          <div className="space-y-4">
            {reviewGroups.map((group) => (
              <FragmentReviewCard
                key={group.entry_id}
                group={group}
                onOpenQuestion={(question, nextGroup) => {
                  setSelectedReviewQuestion(question);
                  setSelectedReviewGroup(nextGroup);
                }}
                onAcceptGroup={(nextGroup) => {
                  const candidate = nextGroup.questions.find((question) => questionIsProblem(question) && question.review.status !== 'accepted');
                  if (candidate) reviewQuestionMutation.mutate({ questionId: candidate.question_id, status: 'accepted' });
                }}
              />
            ))}
            {!reviewGroups.length && (
              <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 text-sm text-[var(--text-muted)] shadow-[var(--shadow-card)]">
                По выбранному фильтру фрагментов нет.
              </section>
            )}
          </div>
          <ApplyAcceptedQuestionsPanel
            acceptedCount={acceptedReviewCount}
            applying={applyAcceptedMutation.isPending}
            onApply={() => {
              if (reviewRunId) applyAcceptedMutation.mutate(reviewRunId);
            }}
          />
          <TechnicalDiagnosticsDisclosure value={review.diagnostics} />
        </>
      ) : (
        <RagEvalResultsPanel
          results={visibleResults}
          loading={statusQuery.isLoading || Boolean(progressJob && !isJobTerminal(progressJob))}
        />
      )}

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
        <div className="mb-4 flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
            <BarChart3 className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">{t('ragEval.lastResult.title')}</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {t('ragEval.lastResult.description')}
            </p>
          </div>
        </div>

        {statusQuery.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('ragEval.lastResult.loadingStatus')}
          </div>
        ) : statusQuery.error ? (
          <div className="flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-500">
            <XCircle className="h-4 w-4" />
            {t('ragEval.lastResult.statusLoadFailed')}
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <h3 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.launch.title')}</h3>
              <div className="rounded-xl bg-[var(--control-bg)] p-4">
                <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">{t('ragEval.launch.status')}</div>
                <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                  {statusLabel(String(latestRunRecord.status || ''))}
                </div>
                <p className="mt-2 text-sm text-[var(--text-muted)]">
                  {t('ragEval.launch.description')}
                </p>
              </div>
              <details className="mt-4 rounded-xl border border-[var(--border-primary)] p-3">
                <summary className="cursor-pointer text-sm font-medium text-[var(--text-primary)]">
                  {t('ragEval.launch.technicalDetails')}
                </summary>
                <div className="mt-3">
                  <ReportJsonBlock value={latestRun} />
                </div>
              </details>
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.report.summaryTitle')}</h3>
              <ReportSummaryCard report={latestReport} />
              <details className="mt-4 rounded-xl border border-[var(--border-primary)] p-3">
                <summary className="cursor-pointer text-sm font-medium text-[var(--text-primary)]">
                  {t('ragEval.report.technicalDetails')}
                </summary>
                <div className="mt-3">
                  <ReportJsonBlock value={Object.keys(latestReport).length ? latestReport : null} />
                </div>
              </details>
            </div>
          </div>
        )}
      </section>

      <ActionableResultsPanel
        results={actionableResults}
        executionSummary={lastActionExecutionSummary}
        executingResultId={executingResultId}
        onExecute={(resultId) => executeActionsMutation.mutate(resultId)}
      />


      <QuestionReviewDrawer
        key={selectedReviewQuestion?.question_id || 'closed'}
        question={selectedReviewQuestion}
        group={selectedReviewGroup}
        mutating={reviewQuestionMutation.isPending || editQuestionMutation.isPending}
        onClose={() => {
          setSelectedReviewQuestion(null);
          setSelectedReviewGroup(null);
        }}
        onAccept={(questionId) => reviewQuestionMutation.mutate({ questionId, status: 'accepted' })}
        onReject={(questionId) => reviewQuestionMutation.mutate({ questionId, status: 'rejected' })}
        onEdit={(questionId, value) => editQuestionMutation.mutate({ questionId, question: value })}
      />
    </div>
  );
};
