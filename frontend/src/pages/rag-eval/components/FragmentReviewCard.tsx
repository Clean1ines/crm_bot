import React from 'react';
import type { RagEvalReviewGroup, RagEvalReviewQuestion } from '@shared/api/modules/ragEval';
import { asStringList } from '../lib/ragEvalResults';
import { questionStatusClass, questionStatusIcon } from '../lib/ragEvalReviewPresentation';
import { formatNumber } from '../lib/ragEvalProgress';

const fragmentReviewStatusLabel = (value: RagEvalReviewGroup['review_status']): string => {
  if (value === 'queued') return 'Ожидает проверки';
  if (value === 'generating_questions') return 'Генерируем вопросы';
  if (value === 'checking_retrieval') return 'Проверяем поиск';
  if (value === 'ready_for_review') return 'Готов к ревью';
  if (value === 'failed') return 'Ошибка проверки';
  return 'Готов к ревью';
};
const fragmentReviewStatusClass = (value: RagEvalReviewGroup['review_status']): string => {
  if (value === 'ready_for_review') return 'bg-emerald-500/10 text-emerald-600';
  if (value === 'failed') return 'bg-red-500/10 text-red-600';
  if (value === 'checking_retrieval') return 'bg-amber-500/10 text-amber-600';
  return 'bg-[var(--control-bg)] text-[var(--text-secondary)]';
};
const asReviewQuestions = (value: unknown): RagEvalReviewQuestion[] => (Array.isArray(value) ? value.filter((item): item is RagEvalReviewQuestion => Boolean(item) && typeof item === 'object') : []);

export const FragmentReviewCard: React.FC<{ group: RagEvalReviewGroup; onOpenQuestion: (question: RagEvalReviewQuestion, group: RagEvalReviewGroup) => void; onAcceptGroup: (group: RagEvalReviewGroup) => void; }> = ({ group, onOpenQuestion, onAcceptGroup }) => {
  const existingQuestions = asStringList(group.existing_questions);
  const proposedImprovements = asStringList(group.proposed_improvements);
  const questions = asReviewQuestions(group.questions);
  const firstQuestion = questions[0] ?? null;
  return (<article className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)]">{/* unchanged markup */}
    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between"><div><h3 className="text-lg font-semibold text-[var(--text-primary)]">Фрагмент · {group.title}</h3><div className="mt-2 flex flex-wrap items-center gap-2"><span className={`rounded-full px-2 py-1 text-xs font-semibold ${fragmentReviewStatusClass(group.review_status)}`}>{fragmentReviewStatusLabel(group.review_status)}</span><span className="text-sm text-[var(--text-muted)]">Статус поиска: {group.status}</span></div>{group.review_status === 'failed' && group.error && (<p className="mt-2 text-sm text-red-500">{group.error}</p>)}</div><span className="rounded-full bg-[var(--control-bg)] px-3 py-1 text-sm font-semibold text-[var(--text-primary)]">{formatNumber(group.problem_count)} проблем</span></div>
    <div className="mt-4 rounded-xl bg-[var(--control-bg)] p-4"><div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">Ответ / знание</div><p className="mt-2 line-clamp-4 text-sm leading-6 text-[var(--text-secondary)]">{group.content || 'Текст фрагмента не найден в текущем поисковом представлении.'}</p></div>
    <div className="mt-4 grid gap-4 lg:grid-cols-2"><div><div className="text-sm font-semibold text-[var(--text-primary)]">Уже есть вопросы</div><ul className="mt-2 space-y-1 text-sm text-[var(--text-secondary)]">{existingQuestions.slice(0, 4).map((item: string) => <li key={item}>— {item}</li>)}{!existingQuestions.length && <li className="text-[var(--text-muted)]">Нет сохранённых вопросов.</li>}</ul></div><div><div className="text-sm font-semibold text-[var(--text-primary)]">Предложение системы</div><ul className="mt-2 space-y-1 text-sm text-[var(--text-secondary)]">{proposedImprovements.map((item: string) => <li key={item}>— {item}</li>)}</ul></div></div>
    <div className="mt-4 space-y-2"><div className="text-sm font-semibold text-[var(--text-primary)]">Сгенерированные вопросы</div>{questions.length === 0 && (<div className="rounded-xl bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-muted)]">Карточка появится здесь, когда вопросы фрагмента будут сгенерированы и проверены.</div>)}{questions.slice(0, 8).map((question) => (<button key={question.question_id} type="button" onClick={() => onOpenQuestion(question, group)} className="flex w-full items-center justify-between gap-3 rounded-xl bg-[var(--control-bg)] px-3 py-2 text-left text-sm hover:bg-[var(--surface-elevated)]"><span className="min-w-0 truncate text-[var(--text-primary)]">{questionStatusIcon(question.retrieval_status)} {question.effective_question}</span><span className={`shrink-0 rounded-full px-2 py-1 text-xs font-semibold ${questionStatusClass(question.retrieval_status)}`}>{question.retrieval_status_label}</span></button>))}</div>
    <div className="mt-4 flex flex-wrap gap-2"><button type="button" onClick={() => firstQuestion && onOpenQuestion(firstQuestion, group)} className="rounded-xl border border-[var(--border-primary)] px-3 py-2 text-sm font-semibold text-[var(--text-primary)]">Рассмотреть вопросы</button><button type="button" onClick={() => onAcceptGroup(group)} className="rounded-xl bg-[var(--accent-primary)] px-3 py-2 text-sm font-semibold text-white">Принять хорошие</button><button type="button" className="rounded-xl border border-[var(--border-primary)] px-3 py-2 text-sm font-semibold text-[var(--text-primary)]">Пересобрать</button></div>
  </article>);
};
