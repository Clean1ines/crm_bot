import React, { useEffect, useRef, useState } from "react";
import { BookOpen, Upload, Search, TestTube2, Loader2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { useParams } from "react-router-dom";
import { getErrorMessage } from "@shared/api/core/errors";
import { knowledgeDocumentStatusLabel } from "@shared/lib/uiLabels";

import {
  KNOWLEDGE_PREPROCESSING_MODE_OPTIONS,
  knowledgeApi,
  type KnowledgePreprocessingMode,
  type KnowledgePreviewResponse,
  type KnowledgePreviewResult,
  type KnowledgeProcessingReport,
  type KnowledgeProcessingAction,
  type KnowledgeImportQualityReport,
  type KnowledgeAnswerDraftsResponse,
  type KnowledgeSourceUnitsResponse,
  type KnowledgePriceFact,
  type KnowledgePriceFactsResponse,
  type KnowledgeCommercialTruthReviewResponse,
  type KnowledgeCommercialTruthReviewPolicy,
  type WorkbenchDocumentCardView,
  type WorkbenchWorkflowLiveStateResponse,
} from "@shared/api/modules/knowledge";
import { BaseModal } from "@shared/ui";
import { t } from "@shared/i18n";
import { CommercialTruthReviewSummary } from "./components/CommercialTruthReviewSummary";
import { DocumentStatusBlock } from "./components/DocumentStatusBlock";
import { KnowledgeDocumentCard } from "./components/KnowledgeDocumentCard";
import { DocumentActionsBlock } from "./components/DocumentActionsBlock";
import { DraftClaimCurationWorkspaceModal } from "./components/DraftClaimCurationWorkspaceModal";
import { AiPlaygroundPanel } from "./components/AiPlaygroundPanel";
import {
  createInitialWorkflowLiveStateResponse,
  reduceWorkflowFrontendProjectionEvent,
} from "./shadow/workflowFrontendProjectionReducer";

type KnowledgeProcessingMetrics = Record<string, unknown>;

type KnowledgeProcessingReportByDocument = Record<
  string,
  KnowledgeProcessingReport
>;
type KnowledgeImportQualityByDocument = Record<
  string,
  KnowledgeImportQualityReport
>;
type KnowledgeAnswerDraftsByDocument = Record<
  string,
  KnowledgeAnswerDraftsResponse
>;
type KnowledgeSourceUnitsByDocument = Record<
  string,
  KnowledgeSourceUnitsResponse
>;
type KnowledgePriceFactsByDocument = Record<
  string,
  KnowledgePriceFactsResponse
>;
type KnowledgeCommercialTruthReviewsByDocument = Record<
  string,
  KnowledgeCommercialTruthReviewResponse
>;
type KnowledgeWorkflowLiveStateByDocument = Record<
  string,
  WorkbenchWorkflowLiveStateResponse
>;

type DraftClaimCurationTarget = {
  documentId: string;
  workflowRunId: string;
  documentName: string;
};

type PriceFactActionVariables = {
  documentId: string;
  factId: string;
  reason?: string;
};

interface Document {
  id: string;
  file_name: string;
  file_size: number;
  status:
    | "pending"
    | "processing"
    | "processed"
    | "error"
    | "cancelled"
    | string;
  error?: string | null;
  created_at: string;
  updated_at?: string | null;
  preprocessing_mode?: KnowledgePreprocessingMode | string | null;
  current_processing_run_id?: string | null;
  card_view?: WorkbenchDocumentCardView | null;
}

const formatSize = (bytes: number) => {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
};

const confidenceLabel = (score: number): string => {
  if (score >= 0.75) return t("knowledge.confidence.high");
  if (score >= 0.45) return t("knowledge.confidence.medium");
  return t("knowledge.confidence.low");
};

const previewTraceLabel = (value: string): string => {
  const labels: Record<string, string> = {
    title: t("knowledge.preview.trace.field.title"),
    questions: t("knowledge.preview.trace.field.questions"),
    synonyms: t("knowledge.preview.trace.field.synonyms"),
    tags: t("knowledge.preview.trace.field.tags"),
    answer: t("knowledge.preview.trace.field.answer"),
    search_text: t("knowledge.preview.trace.field.searchText"),
    embedding_text: t("knowledge.preview.trace.field.embeddingText"),
    exact: t("knowledge.preview.trace.field.exact"),
    embedding: t("knowledge.preview.trace.field.embedding"),
  };

  return labels[value] || value;
};

const formatPreviewScore = (value: number): string =>
  Number.isFinite(value) ? value.toFixed(3) : "0.000";

const DRAFT_FETCH_LIMIT = 1000;
const SOURCE_UNIT_FETCH_LIMIT = 1000;

// Legacy fallback only for display/status of old rows that predate
// backend KnowledgeDocumentLifecycle actions. Do not use this text as
// the primary source for resume/retry/publish/stop action availability.
const STOPPED_BY_USER_ISSUE_NEEDLE =
  "\u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u043c";

const PROCESSING_REPORT_PRIMARY_ACTION_IDS = new Set([
  "resume_processing",
  "publish_ready",
]);

const enabledProcessingReportAction = (
  report: KnowledgeProcessingReport | undefined,
  actionId: string,
): KnowledgeProcessingAction | null =>
  report?.actions.find((action) => action.id === actionId && action.enabled) ??
  null;

const enabledPrimaryProcessingReportActions = (
  report: KnowledgeProcessingReport | undefined,
): KnowledgeProcessingAction[] =>
  report?.actions.filter(
    (action) =>
      action.enabled && PROCESSING_REPORT_PRIMARY_ACTION_IDS.has(action.id),
  ) ?? [];

const formatNumber = (value: number): string =>
  new Intl.NumberFormat("ru-RU").format(value);

const shouldFetchPriceFactsForDocument = (
  doc: Document,
  report: KnowledgeProcessingReport | undefined,
): boolean => {
  if (doc.preprocessing_mode === "price_list") return true;

  const candidateCount = report
    ? metricNumber(report.metrics, "price_acquisition_fact_candidate_count")
    : null;
  const reviewFactCount = report
    ? metricNumber(report.metrics, "price_review_fact_count")
    : null;

  return (candidateCount ?? 0) > 0 || (reviewFactCount ?? 0) > 0;
};

const metricNumber = (
  metrics: KnowledgeProcessingMetrics | null | undefined,
  key: string,
): number | null => {
  const value = metrics?.[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

const cardMetadataRootNumber = (
  doc: Document,
  key: string,
): number => {
  const metadata = doc.card_view?.metadata;
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) return 0;

  const value = (metadata as Record<string, unknown>)[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
};

const workbenchClaimPreviewCount = (doc: Document): number =>
  cardMetadataRootNumber(doc, "workbench_claim_preview_count");

const hasWorkbenchCardArtifacts = (doc: Document): boolean => {
  const cardView = doc.card_view;
  if (!cardView) return false;

  return (
    cardView.registry.entry_count > 0 ||
    cardView.runtime.runtime_entry_count > 0 ||
    workbenchClaimPreviewCount(doc) > 0
  );
};

const processingModelLabel = (_doc: Document): string =>
  t("knowledge.processing.modelPending");

const rawDocumentIssueText = (doc: Document): string | null => {
  const message = doc.error?.trim() || "";
  return message || null;
};

const documentIssueText = (doc: Document): string | null => {
  const message = rawDocumentIssueText(doc);
  if (!message) return null;

  return getErrorMessage(message, t("knowledge.document.failureAdvice"));
};

const isDocumentCancelled = (doc: Document): boolean => {
  if (doc.card_view) {
    return ["cancelled", "paused_manual"].includes(doc.card_view.lifecycle_state);
  }

  const issueText = rawDocumentIssueText(doc)?.toLowerCase() || "";

  return (
    doc.status === "cancelled" ||
    issueText.includes(STOPPED_BY_USER_ISSUE_NEEDLE) ||
    issueText.includes("cancelled") ||
    issueText.includes("canceled")
  );
};

const isDocumentFailed = (doc: Document): boolean => {
  if (doc.card_view) return doc.card_view.lifecycle_state === "failed";
  return doc.status === "error";
};

const workbenchPhaseNumber = (
  doc: Document,
  key: string,
): number => {
  const metadata = doc.card_view?.metadata;
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) return 0;

  const phase = (metadata as Record<string, object | null | undefined>)
    .workbench_phase;
  if (!phase || typeof phase !== "object" || Array.isArray(phase)) return 0;

  const value = (phase as Record<string, unknown>)[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
};

const isDocumentProcessing = (doc: Document): boolean => {
  if (doc.card_view) {
    const lifecycleState = doc.card_view.lifecycle_state;
    if (
      [
        "processing",
        "auto_recovery_scheduled",
      ].includes(lifecycleState)
    ) {
      return true;
    }

    const total = doc.card_view.sections.total;
    const promptACompleted = workbenchPhaseNumber(
      doc,
      "prompt_a_completed_sections",
    );
    const leased = workbenchPhaseNumber(doc, "section_queue_leased_count");
    const ready = workbenchPhaseNumber(doc, "section_queue_ready_count");
    const registryReady = workbenchPhaseNumber(
      doc,
      "registry_application_ready_count",
    );
    const registryLeased = workbenchPhaseNumber(
      doc,
      "registry_application_leased_count",
    );

    return (
      total > 0 &&
      promptACompleted < total &&
      (leased > 0 || ready > 0 || registryReady > 0 || registryLeased > 0)
    );
  }

  return (
    !isDocumentCancelled(doc) &&
    !isDocumentFailed(doc) &&
    (doc.status === "pending" || doc.status === "processing")
  );
};

const knowledgeProcessingModeLabel = (
  mode: string | null | undefined,
): string =>
  KNOWLEDGE_PREPROCESSING_MODE_OPTIONS.find((option) => option.value === mode)
    ?.label ||
  mode ||
  t("knowledge.common.unspecified");

const processingProgressPercent = (doc: Document): number | null => {
  const total = doc.card_view?.sections.total ?? 0;
  if (total <= 0) return null;

  const promptACompleted = workbenchPhaseNumber(
    doc,
    "prompt_a_completed_sections",
  );
  const current =
    promptACompleted > 0
      ? promptACompleted
      : (doc.card_view?.sections.processed ?? 0) +
        (doc.card_view?.sections.failed ?? 0);

  return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
};

const shouldUseWorkflowProjectionForDocument = (doc: Document): boolean => {
  if (doc.current_processing_run_id) return true;
  if (doc.status === "pending" || doc.status === "processing" || doc.status === "error") {
    return true;
  }

  const lifecycleState = doc.card_view?.lifecycle_state ?? "";
  if (
    [
      "processing",
      "auto_recovery_scheduled",
      "failed",
      "cancelled",
      "paused_manual",
    ].includes(lifecycleState)
  ) {
    return true;
  }

  if (isDocumentProcessing(doc)) return true;
  const actions = doc.card_view?.actions ?? [];
  return actions.some(
    (action) =>
      action.visible &&
      (action.action_id === "open_curation" ||
        action.action_id === "resume_processing" ||
        action.action_id === "pause_processing" ||
        action.action_id === "cancel_processing"),
  );
};


const processingProgressLabel = (doc: Document): string => {
  const total = doc.card_view?.sections.total ?? 0;
  if (total <= 0) return t("knowledge.document.preparingProcessing");

  const promptACompleted = workbenchPhaseNumber(
    doc,
    "prompt_a_completed_sections",
  );
  const current =
    promptACompleted > 0
      ? promptACompleted
      : (doc.card_view?.sections.processed ?? 0) +
        (doc.card_view?.sections.failed ?? 0);

  return t("knowledge.progress.stepOf", {
    current: formatNumber(current),
    total: formatNumber(total),
  });
};

const answerResolutionCount = (_doc: Document): number | null => null;

const retightenMetrics = (_doc: Document): KnowledgeProcessingMetrics | null => null;

const retightenStatusText = (
  _metrics: KnowledgeProcessingMetrics,
): string | null => null;

const retightenReportRows = (_doc: Document): string[] => [];

const ANSWER_RESOLUTION_STEP_ID = "answer_resolution";

const positiveMetric = (value: number | null): number | null =>
  value !== null && value > 0 ? value : null;

const sourceChunkCount = (doc: Document): number | null => {
  const total = doc.card_view?.sections.total ?? 0;
  return total > 0 ? total : null;
};

const incomingAnswerCandidateCount = (_doc: Document): number | null => null;

const processingDetailRows = (_doc: Document): string[] => [];

const processingStatusMessage = (doc: Document): string => {
  const cardView = doc.card_view;
  if (cardView?.default_status_description) return cardView.default_status_description;
  if (isDocumentProcessing(doc))
    return t("knowledge.document.draftStatus.processing");
  if (doc.status === "error") return t("knowledge.document.draftStatus.error");
  return t("knowledge.document.draftStatus.ready");
};

const documentLlmTokenText = (doc: Document): string | null => {
  const total = doc.card_view?.usage.total_tokens ?? 0;
  if (total <= 0) return null;

  return t("knowledge.progress.processingUnits", {
    total: formatNumber(total),
  });
};

const documentLlmModels = (_doc: Document): string | null => null;

const formatDurationSeconds = (seconds: number): string => {
  const safeSeconds = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const restSeconds = safeSeconds % 60;

  if (hours > 0) {
    return t("knowledge.duration.hoursMinutesSeconds", {
      hours,
      minutes: minutes.toString().padStart(2, "0"),
      seconds: restSeconds.toString().padStart(2, "0"),
    });
  }
  if (minutes > 0) {
    return t("knowledge.duration.minutesSeconds", {
      minutes,
      seconds: restSeconds.toString().padStart(2, "0"),
    });
  }
  return t("knowledge.duration.seconds", { seconds: restSeconds });
};

const processingElapsedSeconds = (doc: Document, nowMs: number): number => {
  const timer = doc.card_view?.timer;
  if (!timer) return 0;

  const activeElapsed = Math.max(0, timer.active_elapsed_seconds || 0);
  if (timer.mode !== "running" || !timer.current_active_started_at) {
    return activeElapsed;
  }

  const startedAt = Date.parse(timer.current_active_started_at);
  if (!Number.isFinite(startedAt)) return activeElapsed;

  return activeElapsed + Math.max(0, (nowMs - startedAt) / 1000);
};

const PreviewResultCard: React.FC<{
  title: string;
  result: KnowledgePreviewResult;
  compact?: boolean;
  isDebugMode?: boolean;
}> = ({ title, result, compact = false, isDebugMode = false }) => (
  <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
    <div className="mb-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <h3 className="text-sm font-semibold text-[var(--text-primary)]">
        {title}
      </h3>
      <span className="inline-flex w-fit items-center rounded-full bg-[var(--accent-muted)] px-2.5 py-1 text-xs font-medium text-[var(--accent-primary)]">
        {confidenceLabel(result.score)}
      </span>
    </div>
    <p
      className={`text-sm leading-relaxed text-[var(--text-primary)] ${compact ? "line-clamp-3" : ""}`}
    >
      {result.answer || result.content}
    </p>
    <div className="mt-3 flex flex-wrap gap-2 text-xs text-[var(--text-muted)]">
      <span>{t("knowledge.preview.matchFound")}</span>
      {result.source && (
        <span>
          {t("knowledge.preview.sourcePrefix")} {result.source}
        </span>
      )}
      {result.document_status && (
        <span>
          {t("knowledge.preview.documentPrefix")}{" "}
          {knowledgeDocumentStatusLabel(result.document_status)}
        </span>
      )}
      {isDebugMode && result.entry_kind && (
        <span>entry: {result.entry_kind}</span>
      )}
      {isDebugMode && result.trace && (
        <span>
          {t("knowledge.preview.trace.summary", {
            fields:
              result.trace.matched_fields.map(previewTraceLabel).join(", ") ||
              t("knowledge.preview.trace.none"),
            lexical: formatPreviewScore(result.trace.lexical_score),
            vector: formatPreviewScore(result.trace.vector_score),
            final: formatPreviewScore(result.trace.final_score),
            field: previewTraceLabel(result.trace.displayed_field),
          })}
          {" · "}
          {result.trace.is_production_safe
            ? t("knowledge.preview.trace.productionSafe")
            : t("knowledge.preview.trace.notProductionSafe")}
          {result.trace.title_match
            ? ` · ${t("knowledge.preview.trace.titleMatch")}`
            : ""}
          {result.trace.exact_question_match
            ? ` · ${t("knowledge.preview.trace.questionMatch")}`
            : ""}
          {result.trace.length_penalty > 0
            ? ` · ${t("knowledge.preview.trace.penalty", { penalty: formatPreviewScore(result.trace.length_penalty) })}`
            : ""}
        </span>
      )}
    </div>
  </div>
);

export const KnowledgePage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState("");
  const [isSearchFocused, setIsSearchFocused] = useState(false);
  const [previewQuestion, setPreviewQuestion] = useState("");
  const [preprocessingMode, setPreprocessingMode] =
    useState<KnowledgePreprocessingMode>("faq");
  const [isClearModalOpen, setIsClearModalOpen] = useState(false);
  const [deleteDocumentId, setDeleteDocumentId] = useState<string | null>(null);
  const [curationTarget, setDraftClaimCurationTarget] =
    useState<DraftClaimCurationTarget | null>(null);
  const [isDebugMode, setIsDebugMode] = useState(false);
  const [activeKnowledgeTab, setActiveKnowledgeTab] = useState<
    "documents" | "ai_playground"
  >("documents");
  const searchBoxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (!searchBoxRef.current?.contains(target)) {
        setIsSearchFocused(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, []);

  const documentsQuery = useQuery({
    queryKey: ["knowledge-documents", projectId],
    queryFn: async () => {
      if (!projectId) return [];
      const { data } = await knowledgeApi.list(projectId);

      const payload =
        data && typeof data === "object"
          ? (data as Record<string, unknown>)
          : {};
      const list = Array.isArray(payload.documents)
        ? payload.documents
        : Array.isArray(payload.items)
          ? payload.items
          : [];

      return list as Document[];
    },
    enabled: !!projectId,
    retry: false,
    refetchInterval: false,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 30_000,
  });

  const baseDocuments = Array.isArray(documentsQuery.data)
    ? documentsQuery.data
    : [];
  const baseHasProcessingDocuments = baseDocuments.some(isDocumentProcessing);
  const documents = baseDocuments;
  const hasProcessingDocuments = documents.some(isDocumentProcessing);
  const workflowProjectionTargets = documents
    .filter(
      (doc) =>
        Boolean(doc.current_processing_run_id) &&
        shouldUseWorkflowProjectionForDocument(doc),
    )
    .map((doc) => ({
      documentId: doc.id,
      workflowRunId: doc.current_processing_run_id || "",
      fileName: doc.file_name,
      documentStatus: doc.status,
    }))
    .filter((item) => item.workflowRunId.trim().length > 0)
    .sort((left, right) => left.documentId.localeCompare(right.documentId));

  const workflowProjectionDocumentIds = workflowProjectionTargets.map(
    (item) => item.documentId,
  );
  const workflowProjectionSubscriptionKey = workflowProjectionTargets
    .map((item) => `${item.documentId}:${item.workflowRunId}`)
    .join(",");

  const [workflowLiveStates, setWorkflowLiveStates] =
    useState<KnowledgeWorkflowLiveStateByDocument>({});
  const [workflowProjectionErrors, setWorkflowProjectionErrors] = useState<
    Record<string, string | null>
  >({});

  useEffect(() => {
    if (!projectId || workflowProjectionTargets.length === 0) return undefined;

    const stops = workflowProjectionTargets.map((target) => {
      setWorkflowLiveStates((previous) => {
        if (previous[target.documentId]) return previous;

        return {
          ...previous,
          [target.documentId]: createInitialWorkflowLiveStateResponse({
            documentId: target.documentId,
            projectId,
            fileName: target.fileName,
            documentStatus: target.documentStatus,
            workflowRunId: target.workflowRunId,
          }),
        };
      });

      return knowledgeApi.streamFrontendWorkflowEvents(
        projectId,
        target.documentId,
        target.workflowRunId,
        undefined,
        (event) => {
          setWorkflowProjectionErrors((previous) => ({
            ...previous,
            [target.documentId]: null,
          }));

          setWorkflowLiveStates((previous) => {
            const current =
              previous[target.documentId] ??
              createInitialWorkflowLiveStateResponse({
                documentId: target.documentId,
                projectId,
                fileName: target.fileName,
                documentStatus: target.documentStatus,
                workflowRunId: target.workflowRunId,
              });

            return {
              ...previous,
              [target.documentId]: reduceWorkflowFrontendProjectionEvent(
                current,
                event,
              ),
            };
          });

          if (event.projection_type === "workflow_source_units_created") {
            void queryClient.invalidateQueries({
              queryKey: ["knowledge-source-units", projectId],
            });
          }
        },
        (error) => {
          setWorkflowProjectionErrors((previous) => ({
            ...previous,
            [target.documentId]: getErrorMessage(
              error,
              "Не удалось получить события обработки документа",
            ),
          }));
        },
      );
    });

    return () => {
      stops.forEach((stop) => stop());
    };
  }, [
    projectId,
    queryClient,
    workflowProjectionSubscriptionKey,
  ]);


  const reportableDocuments = documents.filter(
    (doc) =>
      !shouldUseWorkflowProjectionForDocument(doc) &&
      (isDocumentProcessing(doc) ||
        isDocumentFailed(doc) ||
        isDocumentCancelled(doc) ||
        hasWorkbenchCardArtifacts(doc)),
  );
  const reportableDocumentIds = reportableDocuments.map((doc) => doc.id).sort();
  const processingReportsQuery = useQuery({
    queryKey: [
      "knowledge-processing-reports",
      projectId,
      reportableDocumentIds.join(","),
    ],
    queryFn: async () => {
      if (!projectId || reportableDocumentIds.length === 0) return {};

      const reports = await Promise.all(
        reportableDocumentIds.map(async (documentId) => {
          try {
            const { data } = await knowledgeApi.progress(projectId, documentId);
            return [documentId, data] as const;
          } catch {
            return null;
          }
        }),
      );

      return reports.reduce<KnowledgeProcessingReportByDocument>(
        (acc, item) => {
          if (item !== null) {
            acc[item[0]] = item[1];
          }
          return acc;
        },
        {},
      );
    },
    enabled:
      !!projectId &&
      reportableDocumentIds.length > 0 &&
      !baseHasProcessingDocuments,
    retry: false,
  });
  const processingReports = processingReportsQuery.data || {};
  const importQualityDocumentIds = hasProcessingDocuments
    ? []
    : documents.map((doc) => doc.id).sort();
  const importQualityReportsQuery = useQuery({
    queryKey: [
      "knowledge-import-quality-reports",
      projectId,
      importQualityDocumentIds.join(","),
    ],
    queryFn: async () => {
      if (!projectId || importQualityDocumentIds.length === 0) return {};

      const reports = await Promise.all(
        importQualityDocumentIds.map(async (documentId) => {
          try {
            const { data } = await knowledgeApi.importQuality(
              projectId,
              documentId,
            );
            return [documentId, data] as const;
          } catch {
            return null;
          }
        }),
      );

      return reports.reduce<KnowledgeImportQualityByDocument>((acc, item) => {
        if (item !== null) {
          acc[item[0]] = item[1];
        }
        return acc;
      }, {});
    },
    enabled: !!projectId && importQualityDocumentIds.length > 0,
    retry: false,
  });
  const importQualityReports = importQualityReportsQuery.data || {};
  const draftPreviewDocumentIds = Array.from(
    new Set([
      ...workflowProjectionDocumentIds,
      ...Object.values(processingReports)
        .filter((report) => {
          const document = documents.find(
            (doc) => doc.id === report.document_id,
          );
          const draftCount =
            metricNumber(report.metrics, "raw_draft_count") ??
            metricNumber(report.metrics, "draft_answer_count") ??
            0;
          const publishedCount =
            metricNumber(report.metrics, "published_answer_count") ?? 0;
          return (
            Boolean(document && isDocumentProcessing(document)) ||
            draftCount > publishedCount
          );
        })
        .map((report) => report.document_id),
    ]),
  ).sort();
  const answerDraftsQuery = useQuery({
    queryKey: [
      "knowledge-answer-drafts",
      projectId,
      draftPreviewDocumentIds.join(","),
      DRAFT_FETCH_LIMIT,
    ],
    queryFn: async () => {
      if (!projectId || draftPreviewDocumentIds.length === 0) return {};

      const drafts = await Promise.all(
        draftPreviewDocumentIds.map(async (documentId) => {
          try {
            const { data } = await knowledgeApi.fragments(
              projectId,
              documentId,
              DRAFT_FETCH_LIMIT,
            );
            return [documentId, data] as const;
          } catch {
            return null;
          }
        }),
      );

      return drafts.reduce<KnowledgeAnswerDraftsByDocument>((acc, item) => {
        if (item !== null) {
          acc[item[0]] = item[1];
        }
        return acc;
      }, {});
    },
    enabled: !!projectId && draftPreviewDocumentIds.length > 0,
    retry: false,
  });
  const answerDrafts = answerDraftsQuery.data || {};
  const sourceUnitDocumentIds = Array.from(
    new Set([
      ...workflowProjectionDocumentIds,
      ...Object.values(processingReports)
        .filter((report) => {
          const document = documents.find(
            (doc) => doc.id === report.document_id,
          );
          const sourceCount =
            metricNumber(report.metrics, "raw_source_unit_count") ??
            metricNumber(report.metrics, "source_unit_count") ??
            (document?.card_view?.sections.total ?? 0);
          return (
            Boolean(document && isDocumentProcessing(document)) ||
            sourceCount > 0
          );
        })
        .map((report) => report.document_id),
    ]),
  ).sort();
  const sourceUnitsQuery = useQuery({
    queryKey: [
      "knowledge-source-units",
      projectId,
      sourceUnitDocumentIds.join(","),
      SOURCE_UNIT_FETCH_LIMIT,
    ],
    queryFn: async () => {
      if (!projectId || sourceUnitDocumentIds.length === 0) return {};

      const sourceUnits = await Promise.all(
        sourceUnitDocumentIds.map(async (documentId) => {
          try {
            const { data } = await knowledgeApi.sourceUnits(
              projectId,
              documentId,
              SOURCE_UNIT_FETCH_LIMIT,
            );
            return [documentId, data] as const;
          } catch {
            return null;
          }
        }),
      );

      return sourceUnits.reduce<KnowledgeSourceUnitsByDocument>((acc, item) => {
        if (item !== null) {
          acc[item[0]] = item[1];
        }
        return acc;
      }, {});
    },
    enabled: !!projectId && sourceUnitDocumentIds.length > 0,
    retry: false,
  });
  const sourceUnits = sourceUnitsQuery.data || {};
  const priceFactDocumentIds = hasProcessingDocuments
    ? []
    : documents
        .filter((doc) =>
          shouldFetchPriceFactsForDocument(doc, processingReports[doc.id]),
        )
        .map((doc) => doc.id)
        .sort();
  const priceFactsQuery = useQuery({
    queryKey: [
      "knowledge-price-facts",
      projectId,
      priceFactDocumentIds.join(","),
    ],
    queryFn: async () => {
      if (!projectId || priceFactDocumentIds.length === 0) return {};

      const priceFacts = await Promise.all(
        priceFactDocumentIds.map(async (documentId) => {
          try {
            const { data } = await knowledgeApi.priceFacts(
              projectId,
              documentId,
            );
            return [documentId, data] as const;
          } catch {
            return null;
          }
        }),
      );

      return priceFacts.reduce<KnowledgePriceFactsByDocument>((acc, item) => {
        if (item !== null) {
          acc[item[0]] = item[1];
        }
        return acc;
      }, {});
    },
    enabled: !!projectId && priceFactDocumentIds.length > 0,
    retry: false,
  });
  const priceFacts = priceFactsQuery.data || {};
  const [commercialTruthReviewPolicy, setCommercialTruthReviewPolicy] =
    useState<KnowledgeCommercialTruthReviewPolicy>("manual_review");
  const projectCommercialTruthReviewQuery = useQuery({
    queryKey: [
      "project-commercial-truth-review",
      projectId,
      commercialTruthReviewPolicy,
    ],
    queryFn: async () => {
      if (!projectId) return undefined;

      const { data } = await knowledgeApi.projectCommercialTruthReview(
        projectId,
        commercialTruthReviewPolicy,
      );
      return data;
    },
    enabled: !!projectId && !hasProcessingDocuments,
    retry: false,
  });
  const commercialTruthReviewQuery = useQuery({
    queryKey: [
      "knowledge-commercial-truth-review",
      projectId,
      priceFactDocumentIds.join(","),
      commercialTruthReviewPolicy,
    ],
    queryFn: async () => {
      if (!projectId || priceFactDocumentIds.length === 0) return {};

      const reviews = await Promise.all(
        priceFactDocumentIds.map(async (documentId) => {
          try {
            const { data } = await knowledgeApi.commercialTruthReview(
              projectId,
              documentId,
              commercialTruthReviewPolicy,
            );
            return [documentId, data] as const;
          } catch {
            return null;
          }
        }),
      );

      return reviews.reduce<KnowledgeCommercialTruthReviewsByDocument>(
        (acc, item) => {
          if (item !== null) {
            acc[item[0]] = item[1];
          }
          return acc;
        },
        {},
      );
    },
    enabled:
      !!projectId && priceFactDocumentIds.length > 0 && !hasProcessingDocuments,
    retry: false,
  });
  const commercialTruthReviews = commercialTruthReviewQuery.data || {};
  const deleteDocument = deleteDocumentId
    ? (documents.find((doc) => doc.id === deleteDocumentId) ?? null)
    : null;
  const deleteDocumentConfirmation =
    deleteDocument?.card_view?.actions.find(
      (action) => action.action_id === "delete_document",
    )?.default_confirmation ||
    `Документ «${deleteDocument?.file_name || "этот документ"}» и все связанные артефакты будут удалены из базы. Это действие нельзя отменить.`;

  const projectCommercialTruthRef = useRef<HTMLDivElement | null>(null);
  const documentsGridRef = useRef<HTMLDivElement | null>(null);

  const removeDocumentLocalState = (documentId: string): void => {
    setDraftClaimCurationTarget((current) =>
      current?.documentId === documentId ? null : current,
    );
  };
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const [processingNowMs, setProcessingNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (!hasProcessingDocuments) return undefined;

    const timer = window.setInterval(() => {
      setProcessingNowMs(Date.now());
    }, 1000);

    return () => window.clearInterval(timer);
  }, [hasProcessingDocuments]);

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      if (!projectId) throw new Error(t("knowledge.errors.projectIdMissing"));

      const response = await knowledgeApi.upload(
        projectId,
        file,
        preprocessingMode,
      );

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(
          getErrorMessage(
            errData,
            t("knowledge.feedback.uploadDocumentFailed"),
          ),
        );
      }

      return await response.json();
    },
    onSuccess: async () => {
      toast.success(t("knowledge.feedback.documentQueued"));
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-documents", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-usage", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-processing-reports", projectId],
      });
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, t("knowledge.feedback.uploadError")));
    },
  });

  const previewMutation = useMutation<
    KnowledgePreviewResponse,
    unknown,
    string
  >({
    mutationFn: async (question: string) => {
      if (!projectId) throw new Error(t("knowledge.errors.projectIdMissing"));
      const { data } = await knowledgeApi.preview(projectId, question, 5);
      return data;
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, t("knowledge.feedback.previewFailed")));
    },
  });

  const clearMutation = useMutation({
    mutationFn: async () => {
      if (!projectId) throw new Error(t("knowledge.errors.projectIdMissing"));
      await knowledgeApi.clear(projectId);
    },
    onSuccess: async () => {
      setIsClearModalOpen(false);
      setPreviewQuestion("");
      previewMutation.reset();
      toast.success(t("knowledge.feedback.cleared"));
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-documents", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-usage", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-processing-reports", projectId],
      });
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, t("knowledge.feedback.clearFailed")));
    },
  });

  const deleteDocumentMutation = useMutation<string, unknown, string>({
    mutationFn: async (documentId: string) => {
      if (!projectId) throw new Error(t("knowledge.errors.projectIdMissing"));
      await knowledgeApi.deleteDocument(projectId, documentId);
      return documentId;
    },
    onSuccess: async (documentId) => {
      setDeleteDocumentId(null);
      removeDocumentLocalState(documentId);
      toast.success("Документ удалён");

      await queryClient.invalidateQueries({
        queryKey: ["knowledge-documents", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-usage", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-processing-reports", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-import-quality-reports", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-answer-drafts", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-source-units", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-price-facts", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["project-commercial-truth-review", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-commercial-truth-review", projectId],
      });
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, "Не удалось удалить документ"));
    },
  });

  const pauseProcessingMutation = useMutation({
    mutationFn: async (documentId: string) => {
      if (!projectId) throw new Error(t("knowledge.errors.projectIdMissing"));
      await knowledgeApi.cancel(projectId, documentId);
    },
    onSuccess: async () => {
      toast.success("Обработка документа поставлена на паузу");
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-documents", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-processing-reports", projectId],
      });
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, "Не удалось поставить обработку на паузу"));
    },
  });

  const cancelProcessingMutation = useMutation({
    mutationFn: async (documentId: string) => {
      if (!projectId) throw new Error(t("knowledge.errors.projectIdMissing"));
      await knowledgeApi.cancel(projectId, documentId);
    },
    onSuccess: async () => {
      toast.success(t("knowledge.feedback.processingStopped"));
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-documents", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-usage", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-processing-reports", projectId],
      });
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, t("knowledge.feedback.stopFailed")));
    },
  });

  const resumeProcessingMutation = useMutation({
    mutationFn: async (documentId: string) => {
      if (!projectId) throw new Error(t("knowledge.errors.projectIdMissing"));
      await knowledgeApi.resumeProcessing(projectId, documentId);
    },
    onSuccess: async () => {
      toast.success("Обработка документа возобновлена");
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-documents", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-usage", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-processing-reports", projectId],
      });
    },
    onError: (err: unknown) => {
      toast.error(
        getErrorMessage(err, "Не удалось возобновить обработку документа"),
      );
    },
  });

  const confirmDegradedFallbackMutation = useMutation({
    mutationFn: async (workflowRunId: string) => {
      if (!projectId) throw new Error(t("knowledge.errors.projectIdMissing"));
      await knowledgeApi.confirmDegradedFallback(projectId, workflowRunId);
    },
    onSuccess: async () => {
      toast.success("Обработка продолжена на подтверждённой fallback-модели");
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-documents", projectId],
      });
    },
    onError: (err: unknown) => {
      toast.error(
        getErrorMessage(err, "Не удалось подтвердить fallback-модель"),
      );
    },
  });

  const publishReadyMutation = useMutation({
    mutationFn: async (documentId: string) => {
      if (!projectId) throw new Error(t("knowledge.errors.projectIdMissing"));
      await knowledgeApi.publishReady(projectId, documentId);
    },
    onSuccess: async () => {
      toast.success(t("knowledge.feedback.publishReadyQueued"));
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-documents", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-usage", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-processing-reports", projectId],
      });
    },
    onError: (err: unknown) => {
      toast.error(
        getErrorMessage(err, t("knowledge.feedback.publishReadyFailed")),
      );
    },
  });

  const priceFactActionMutation = useMutation<
    "publish" | "reject",
    unknown,
    PriceFactActionVariables
  >({
    mutationFn: async ({ documentId, factId, reason }) => {
      if (!projectId) throw new Error(t("knowledge.errors.projectIdMissing"));

      if (reason !== undefined) {
        await knowledgeApi.rejectPriceFacts(projectId, documentId, {
          fact_ids: [factId],
          reason,
        });
        return "reject";
      }

      await knowledgeApi.publishPriceFacts(projectId, documentId, {
        fact_ids: [factId],
      });
      return "publish";
    },
    onSuccess: async (action) => {
      toast.success(
        action === "reject"
          ? t("knowledge.priceFacts.actions.rejectSuccess")
          : t("knowledge.priceFacts.actions.publishSuccess"),
      );
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-price-facts", projectId],
      });
    },
    onError: (err: unknown, variables) => {
      toast.error(
        getErrorMessage(
          err,
          variables.reason !== undefined
            ? t("knowledge.priceFacts.actions.rejectFailed")
            : t("knowledge.priceFacts.actions.publishFailed"),
        ),
      );
    },
  });

  const handlePublishPriceFact = (
    documentId: string,
    fact: KnowledgePriceFact,
  ): void => {
    priceFactActionMutation.mutate({
      documentId,
      factId: fact.id,
    });
  };

  const handleRejectPriceFact = (
    documentId: string,
    fact: KnowledgePriceFact,
  ): void => {
    const reason = window.prompt(
      t("knowledge.priceFacts.actions.reasonPlaceholder"),
      "",
    );
    if (reason === null) return;

    const cleanedReason = reason.trim();
    if (!cleanedReason) {
      toast.error(t("knowledge.priceFacts.actions.rejectReasonRequired"));
      return;
    }

    priceFactActionMutation.mutate({
      documentId,
      factId: fact.id,
      reason: cleanedReason,
    });
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadMutation.mutate(file);
    }
  };

  const triggerUpload = () => {
    fileInputRef.current?.click();
  };

  const handlePreviewSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const question = previewQuestion.trim();
    if (!question) {
      toast.error(t("knowledge.feedback.enterClientQuestion"));
      return;
    }
    previewMutation.mutate(question);
  };

  const handleDragOver = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
  };

  const handleDrop = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();

    const file = event.dataTransfer.files?.[0];
    if (file) {
      uploadMutation.mutate(file);
    }
  };

  if (documentsQuery.isLoading) {
    return (
      <div className="flex justify-center p-4 text-sm text-[var(--text-muted)] sm:p-6 lg:p-8">
        {t("knowledge.loading")}
      </div>
    );
  }

  const normalizedSearchQuery = searchQuery.trim().toLowerCase();
  const startsWithMatches = documents.filter((doc) =>
    doc.file_name.toLowerCase().startsWith(normalizedSearchQuery),
  );
  const fallbackIncludesMatches = documents.filter(
    (doc) =>
      !doc.file_name.toLowerCase().startsWith(normalizedSearchQuery) &&
      doc.file_name.toLowerCase().includes(normalizedSearchQuery),
  );
  const filteredDocuments =
    normalizedSearchQuery.length === 0
      ? documents
      : startsWithMatches.length > 0
        ? startsWithMatches
        : fallbackIncludesMatches;
  const searchSuggestions =
    normalizedSearchQuery.length > 0 ? filteredDocuments.slice(0, 8) : [];

  const previewResult = previewMutation.data;

  const getStatusBadge = (doc: Document) => {
    const status = doc.status;

    if (isDocumentCancelled(doc)) {
      return {
        label: t("knowledge.status.stopped"),
        className: "bg-[var(--accent-warning-bg)] text-[var(--accent-warning)]",
      };
    }
    if (isDocumentFailed(doc)) {
      return {
        label: t("knowledge.status.error"),
        className:
          "bg-[var(--accent-danger-bg)] text-[var(--accent-danger-text)]",
      };
    }
    if (isDocumentProcessing(doc)) {
      return {
        label: t("knowledge.status.processing"),
        className: "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]",
      };
    }
    if (status === "processed") {
      return {
        label: t("knowledge.status.processed"),
        className:
          "bg-[var(--accent-success-bg)] text-[var(--accent-success-text)]",
      };
    }
    return {
      label: t("knowledge.status.queued"),
      className: "bg-[var(--accent-warning-bg)] text-[var(--accent-warning)]",
    };
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8 animate-in fade-in duration-500">
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileSelect}
        className="hidden"
        accept=".pdf,.json,.md,.txt"
      />

      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="mb-2 text-2xl font-semibold leading-tight text-[var(--text-primary)] sm:text-3xl">
            {t("knowledge.title")}
          </h1>
          <p className="text-[var(--text-muted)]">
            {t("knowledge.description")}
          </p>
        </div>
        <div className="flex w-full flex-col gap-3 sm:flex-row lg:w-auto">
          <div ref={searchBoxRef} className="relative">
            <div className="pointer-events-none absolute inset-y-0 left-3 flex items-center">
              <Search className="h-4 w-4 text-[var(--text-muted)]" />
            </div>
            <input
              type="text"
              placeholder={t("knowledge.search.placeholder")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onFocus={() => setIsSearchFocused(true)}
              className="min-h-10 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--control-bg)] py-2 pl-10 pr-4 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] transition-all placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 lg:w-64"
            />
            {isSearchFocused && searchSuggestions.length > 0 && (
              <div className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-1 shadow-[var(--shadow-heavy)] lg:w-64">
                {searchSuggestions.map((doc) => (
                  <button
                    key={doc.id}
                    type="button"
                    onClick={() => {
                      setSearchQuery(doc.file_name);
                      setIsSearchFocused(false);
                      document
                        .getElementById(`knowledge-doc-card-${doc.id}`)
                        ?.scrollIntoView({
                          behavior: "smooth",
                          block: "center",
                        });
                    }}
                    className="w-full rounded-lg px-3 py-2 text-left text-sm text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]"
                  >
                    {doc.file_name}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={() => setIsDebugMode((current) => !current)}
            aria-pressed={isDebugMode}
            title={t("knowledge.debugMode.toggleTitle")}
            className="inline-flex min-h-10 items-center justify-center rounded-lg bg-[var(--surface-secondary)] px-4 py-2 text-sm font-medium text-[var(--text-muted)] shadow-[var(--shadow-sm)] transition-colors hover:bg-[var(--control-bg)]"
          >
            {isDebugMode
              ? t("knowledge.debugMode.on")
              : t("knowledge.debugMode.off")}
          </button>
          <button
            type="button"
            onClick={() => setIsClearModalOpen(true)}
            className="inline-flex min-h-10 items-center justify-center rounded-lg bg-[var(--accent-danger-bg)] px-4 py-2 text-sm font-medium text-[var(--accent-danger-text)] shadow-[var(--shadow-sm)] transition-colors hover:bg-[var(--accent-danger-bg)]/80"
          >
            {t("knowledge.actions.clear")}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 rounded-2xl bg-[var(--surface-elevated)] p-2 shadow-sm">
        <button
          type="button"
          onClick={() => setActiveKnowledgeTab("documents")}
          className={`rounded-xl px-4 py-2 text-sm font-semibold transition-colors ${
            activeKnowledgeTab === "documents"
              ? "bg-[var(--accent-primary)] text-white"
              : "text-[var(--text-muted)] hover:bg-[var(--surface-secondary)]"
          }`}
        >
          Документы
        </button>
        <button
          type="button"
          onClick={() => setActiveKnowledgeTab("ai_playground")}
          className={`rounded-xl px-4 py-2 text-sm font-semibold transition-colors ${
            activeKnowledgeTab === "ai_playground"
              ? "bg-[var(--accent-primary)] text-white"
              : "text-[var(--text-muted)] hover:bg-[var(--surface-secondary)]"
          }`}
        >
          Проверка AI-запроса
        </button>
      </div>

      {activeKnowledgeTab === "ai_playground" ? (
        <AiPlaygroundPanel projectId={projectId || ""} />
      ) : (
        <>
      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-sm sm:p-5 lg:p-6">
        <div className="mb-4 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              {t("knowledge.upload.title")}
            </h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {t("knowledge.upload.description")}
            </p>
          </div>

          <label className="flex w-full flex-col gap-2 lg:w-80">
            <span className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
              {t("knowledge.upload.preprocessingMode")}
            </span>
            <select
              value={preprocessingMode}
              onChange={(event) =>
                setPreprocessingMode(
                  event.target.value as KnowledgePreprocessingMode,
                )
              }
              disabled={uploadMutation.isPending}
              className="min-h-11 rounded-xl border border-[var(--border-subtle)] bg-[var(--control-bg)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 disabled:cursor-wait disabled:opacity-60"
            >
              {KNOWLEDGE_PREPROCESSING_MODE_OPTIONS.filter(
                (option) =>
                  option.value === "faq" || option.value === "price_list",
              ).map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <span className="text-xs leading-relaxed text-[var(--text-muted)]">
              {
                KNOWLEDGE_PREPROCESSING_MODE_OPTIONS.find(
                  (option) => option.value === preprocessingMode,
                )?.description
              }
            </span>
          </label>
        </div>

        {hasProcessingDocuments && (
          <div className="mb-4 rounded-2xl bg-[var(--accent-primary)]/10 p-4 text-sm text-[var(--text-primary)]">
            <div className="flex items-start gap-3">
              <Loader2 className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-[var(--accent-primary)]" />
              <div>
                <div className="font-semibold">
                  {t("knowledge.processing.title")}
                </div>
                <p className="mt-1 leading-relaxed text-[var(--text-muted)]">
                  {t("knowledge.processing.descriptionLine1")}
                  {t("knowledge.processing.descriptionLine2")}
                  {t("knowledge.processing.descriptionLine3")}
                </p>
              </div>
            </div>
          </div>
        )}

        <div
          onClick={triggerUpload}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl bg-[var(--surface-card)] p-6 shadow-sm transition-colors group sm:p-8 lg:p-12 ${
            uploadMutation.isPending
              ? "border-[var(--accent-primary)] bg-[var(--accent-primary)]/5 cursor-wait"
              : "border-[var(--border-subtle)] hover:bg-[var(--surface-secondary)]"
          }`}
        >
          <div
            className={`mb-4 flex h-14 w-14 items-center justify-center rounded-full transition-transform sm:h-16 sm:w-16 ${
              uploadMutation.isPending
                ? "bg-[var(--accent-primary)]/20 animate-pulse"
                : "bg-[var(--accent-primary)]/10 group-hover:scale-110"
            }`}
          >
            <Upload className="h-7 w-7 text-[var(--accent-primary)] sm:h-8 sm:w-8" />
          </div>
          <h3 className="text-center text-base font-semibold text-[var(--text-primary)] sm:text-lg">
            {uploadMutation.isPending
              ? t("common.states.loading")
              : t("knowledge.upload.dropzoneText")}
          </h3>
          <p className="mt-1 text-center text-sm text-[var(--text-muted)]">
            {t("knowledge.upload.acceptedFormats")} ·{" "}
            {
              KNOWLEDGE_PREPROCESSING_MODE_OPTIONS.find(
                (option) => option.value === preprocessingMode,
              )?.label
            }
          </p>
        </div>
      </section>

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-sm sm:p-5 lg:p-6">
        <div className="mb-4 flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
            <TestTube2 className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              {t("knowledge.preview.title")}
            </h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {t("knowledge.preview.description")}
            </p>
          </div>
        </div>

        <form
          onSubmit={handlePreviewSubmit}
          className="flex flex-col gap-3 lg:flex-row"
        >
          <textarea
            value={previewQuestion}
            onChange={(event) => setPreviewQuestion(event.target.value)}
            placeholder={t("knowledge.preview.placeholder")}
            rows={3}
            className="min-h-24 flex-1 resize-y rounded-xl bg-[var(--control-bg)] px-4 py-3 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          />
          <button
            type="submit"
            disabled={previewMutation.isPending}
            className="min-h-11 rounded-xl bg-[var(--accent-primary)] px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-[var(--accent-hover)] disabled:cursor-wait disabled:opacity-60 lg:self-start"
          >
            {previewMutation.isPending
              ? t("knowledge.preview.checking")
              : t("knowledge.preview.check")}
          </button>
        </form>

        {previewResult && (
          <div className="mt-5 space-y-4">
            {previewResult.is_empty || !previewResult.best_result ? (
              <div className="rounded-xl bg-[var(--surface-secondary)] p-4 text-sm text-[var(--text-muted)]">
                {t("knowledge.preview.noResults")}
              </div>
            ) : (
              <>
                <PreviewResultCard
                  title={t("knowledge.preview.bestAnswer")}
                  result={previewResult.best_result}
                  isDebugMode={isDebugMode}
                />
                {previewResult.top_results.length > 1 && (
                  <div className="space-y-3">
                    <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                      {t("knowledge.preview.topMatches")}
                    </h3>
                    {previewResult.top_results.slice(1).map((result) => (
                      <PreviewResultCard
                        key={result.id}
                        title={t("knowledge.preview.additionalMatch")}
                        result={result}
                        compact
                        isDebugMode={isDebugMode}
                      />
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </section>

      {documents.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl bg-[var(--surface-secondary)] p-6 text-center sm:p-10 lg:p-16">
          <BookOpen className="mb-4 h-12 w-12 text-[var(--border-subtle)] sm:h-16 sm:w-16" />
          <h3 className="text-lg font-semibold text-[var(--text-primary)] sm:text-xl">
            {t("knowledge.empty.title")}
          </h3>
          <p className="mt-2 text-[var(--text-muted)]">
            {t("knowledge.empty.description")}
          </p>
        </div>
      ) : (
        <>
          <div
            ref={projectCommercialTruthRef}
            id="knowledge-project-commercial-truth"
          >
            <CommercialTruthReviewSummary
              response={projectCommercialTruthReviewQuery.data}
              isLoading={
                projectCommercialTruthReviewQuery.isLoading ||
                (projectCommercialTruthReviewQuery.isFetching &&
                  !projectCommercialTruthReviewQuery.data)
              }
              policy={commercialTruthReviewPolicy}
              onPolicyChange={setCommercialTruthReviewPolicy}
            />
          </div>

          <div
            ref={documentsGridRef}
            id="knowledge-documents-grid"
            className="grid grid-cols-1 gap-6"
          >
            {filteredDocuments.map((doc) => {
              const statusBadge = getStatusBadge(doc);
              const processingReport = processingReports[doc.id];
              const importQualityReport = importQualityReports[doc.id];
              const priceFactsResponse = priceFacts[doc.id];
              const commercialTruthReviewResponse =
                commercialTruthReviews[doc.id];
              const shouldLoadPriceFacts = priceFactDocumentIds.includes(
                doc.id,
              );
              const isPriceFactsLoading =
                shouldLoadPriceFacts &&
                (priceFactsQuery.isLoading ||
                  (priceFactsQuery.isFetching && !priceFactsResponse));
              const isCommercialTruthReviewLoading =
                shouldLoadPriceFacts &&
                (commercialTruthReviewQuery.isLoading ||
                  (commercialTruthReviewQuery.isFetching &&
                    !commercialTruthReviewResponse));
              const mutatingPriceFactId =
                priceFactActionMutation.variables?.documentId === doc.id
                  ? priceFactActionMutation.variables.factId
                  : null;
              const canCancelProcessing = Boolean(
                enabledProcessingReportAction(processingReport, "cancel"),
              );
              const primaryProcessingReportActions =
                enabledPrimaryProcessingReportActions(processingReport);

              return (
                <KnowledgeDocumentCard
                  key={doc.id}
                  doc={doc}
                  isDeletePending={
                    deleteDocumentMutation.isPending &&
                    deleteDocumentMutation.variables === doc.id
                  }
                  onRequestDelete={() => setDeleteDocumentId(doc.id)}
                  onOpenCuration={(workflowRunId) => {
                    if (workflowRunId) {
                      setDraftClaimCurationTarget({
                        documentId: doc.id,
                        workflowRunId,
                        documentName: doc.file_name,
                      });
                      return;
                    }
                    toast.error("Не удалось открыть текущую рабочую область курации");
                  }}
                  workflowLiveState={workflowLiveStates[doc.id] ?? null}
                  workflowLiveStateLoading={
                    workflowProjectionDocumentIds.includes(doc.id) &&
                    !(workflowLiveStates[doc.id] ?? null)
                  }
                  workflowLiveStateError={workflowProjectionErrors[doc.id] ?? null}
                  sourceUnitsResponse={sourceUnits[doc.id] ?? null}
                  answerDraftsResponse={answerDrafts[doc.id] ?? null}
                  onCardAction={(actionId) => {
                    if (actionId === "pause_processing") {
                      pauseProcessingMutation.mutate(doc.id);
                      return;
                    }
                    if (actionId === "cancel_processing") {
                      cancelProcessingMutation.mutate(doc.id);
                      return;
                    }
                    if (actionId === "cancel_scheduled_recovery") {
                      cancelProcessingMutation.mutate(doc.id);
                      return;
                    }
                    if (actionId === "resume_processing") {
                      resumeProcessingMutation.mutate(doc.id);
                      return;
                    }
                    if (actionId === "confirm_degraded_fallback") {
                      const workflowRunId =
                        workflowLiveStates[doc.id]?.workflow.workflow_run_id ??
                        null;
                      if (workflowRunId) {
                        confirmDegradedFallbackMutation.mutate(workflowRunId);
                        return;
                      }
                      toast.error("Не удалось определить workflow для продолжения");
                      return;
                    }
                    if (actionId === "publish_ready") {
                      publishReadyMutation.mutate(doc.id);
                      return;
                    }
                    if (actionId === "open_curation") {
                      const workflowRunId =
                        workflowLiveStates[doc.id]?.workflow.curation.workflow_run_id ??
                        workflowLiveStates[doc.id]?.workflow.workflow_run_id ??
                        null;
                      if (workflowRunId) {
                        setDraftClaimCurationTarget({
                          documentId: doc.id,
                          workflowRunId,
                          documentName: doc.file_name,
                        });
                        return;
                      }
                      toast.error("Не удалось открыть текущую рабочую область курации");
                      return;
                    }
                    if (actionId === "open_published_surfaces") {
                      toast.error("Не удалось открыть текущую рабочую область курации");
                      return;
                    }
                    if (actionId === "delete_document") {
                      setDeleteDocumentId(doc.id);
                      return;
                    }
                    if (actionId === "open_workbench") {
                      toast.error("Не удалось открыть текущую рабочую область курации");
                    }
                  }}
                  formatSize={formatSize}
                  knowledgeProcessingModeLabel={knowledgeProcessingModeLabel}
                />
              );
            })}
          </div>
        </>
      )}
        </>
      )}


      {curationTarget && projectId && (
        <DraftClaimCurationWorkspaceModal
          projectId={projectId}
          workflowRunId={curationTarget.workflowRunId}
          documentName={curationTarget.documentName}
          onClose={() => setDraftClaimCurationTarget(null)}
        />
      )}


      <BaseModal
        isOpen={deleteDocumentId !== null}
        onClose={() => {
          if (!deleteDocumentMutation.isPending) {
            setDeleteDocumentId(null);
          }
        }}
        title="Удалить документ"
        cancelLabel={t("common.actions.cancel")}
      >
        <p className="text-sm leading-relaxed text-[var(--text-primary)]">
          {deleteDocumentConfirmation}
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => {
              if (deleteDocumentId) {
                deleteDocumentMutation.mutate(deleteDocumentId);
              }
            }}
            disabled={deleteDocumentMutation.isPending || deleteDocumentId === null}
            className="min-h-9 rounded-lg bg-[var(--accent-danger)] px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-[var(--accent-danger-text)] disabled:opacity-40 focus:outline-none focus:ring-2 focus:ring-[var(--accent-danger)]/25"
          >
            {deleteDocumentMutation.isPending
              ? "Удаляем..."
              : t("common.actions.delete")}
          </button>
        </div>
      </BaseModal>

      <BaseModal
        isOpen={isClearModalOpen}
        onClose={() => {
          if (!clearMutation.isPending) {
            setIsClearModalOpen(false);
          }
        }}
        title={t("knowledge.actions.clear")}
        cancelLabel={t("common.actions.cancel")}
      >
        <p className="text-sm leading-relaxed text-[var(--text-primary)]">
          {t("knowledge.clearModal.confirm")}
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => clearMutation.mutate()}
            disabled={clearMutation.isPending}
            className="min-h-9 rounded-lg bg-[var(--accent-danger)] px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-[var(--accent-danger-text)] disabled:opacity-40 focus:outline-none focus:ring-2 focus:ring-[var(--accent-danger)]/25"
          >
            {clearMutation.isPending
              ? t("knowledge.clearModal.clearing")
              : t("knowledge.clearModal.clear")}
          </button>
        </div>
      </BaseModal>
    </div>
  );
};
