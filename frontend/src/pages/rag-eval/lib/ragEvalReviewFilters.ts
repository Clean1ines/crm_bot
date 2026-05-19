import type { RagEvalReviewGroup, RagEvalReviewQuestion } from '@shared/api/modules/ragEval';

export type EvalReviewFilter = 'all' | 'problematic' | 'wrong_top1' | 'missing' | 'good_candidates' | 'fallback' | 'typo_short_vague';
export type EvalReviewSort = 'most_problematic' | 'most_questions' | 'worst_confusion' | 'best_candidates';

export const REVIEW_FILTERS: Array<{ id: EvalReviewFilter; label: string }> = [
  { id: 'all', label: 'Все фрагменты' },
  { id: 'problematic', label: 'Только проблемные' },
  { id: 'wrong_top1', label: 'Только wrong top-1' },
  { id: 'missing', label: 'Только не найденные' },
  { id: 'good_candidates', label: 'Хорошие кандидаты' },
  { id: 'fallback', label: 'Fallback-generated' },
  { id: 'typo_short_vague', label: 'Typo / short / vague' },
];

export const REVIEW_SORTS: Array<{ id: EvalReviewSort; label: string }> = [
  { id: 'most_problematic', label: 'Сначала самые проблемные' },
  { id: 'most_questions', label: 'Сначала больше вопросов' },
  { id: 'worst_confusion', label: 'Сначала worst top-1 confusion' },
  { id: 'best_candidates', label: 'Сначала хорошие кандидаты' },
];

export const questionIsProblem = (question: RagEvalReviewQuestion): boolean => question.retrieval_status !== 'reliable';

export const groupMatchesFilter = (group: RagEvalReviewGroup, filter: EvalReviewFilter): boolean => {
  if (filter === 'all') return true;
  if (filter === 'problematic') return group.problem_count > 0;
  if (filter === 'wrong_top1') return group.questions.some((question) => question.wrong_entry_top1);
  if (filter === 'missing') return group.questions.some((question) => question.retrieval_status === 'missing');
  if (filter === 'good_candidates') return group.questions.some((question) => questionIsProblem(question) && question.review.status !== 'rejected');
  if (filter === 'fallback') return group.questions.some((question) => question.fallback_generated);
  if (filter === 'typo_short_vague') return group.questions.some((question) => question.question_type === 'short_vague');
  return true;
};

export const sortReviewGroups = (groups: RagEvalReviewGroup[], sort: EvalReviewSort): RagEvalReviewGroup[] => {
  const copy = [...groups];
  copy.sort((left, right) => {
    if (sort === 'most_questions') return right.question_count - left.question_count;
    if (sort === 'worst_confusion') {
      const rightConfused = right.questions.filter((question) => question.wrong_entry_top1).length;
      const leftConfused = left.questions.filter((question) => question.wrong_entry_top1).length;
      return rightConfused - leftConfused || right.problem_count - left.problem_count;
    }
    if (sort === 'best_candidates') return right.improvement_count - left.improvement_count || right.problem_count - left.problem_count;
    return right.problem_count - left.problem_count || right.improvement_count - left.improvement_count;
  });
  return copy;
};
