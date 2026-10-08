export const BUSINESS_PLAN_STEPS = [
  { key: 'refine', label: '계획 정리' },
  { key: 'setup', label: '공고 양식 선택' },
  { key: 'supplement', label: '계획 보완' },
  { key: 'preview', label: '초안 평가' },
  { key: 'improve', label: '초안 수정' },
  { key: 'done', label: '재평가 및 저장' },
];

export function getBusinessPlanResumeStep(draft) {
  const hasSupplement = !!draft.templateInfo && (draft.fieldAnalysis || []).some((field) =>
    ['partial', 'missing', 'unsupported'].includes(field.status) || field.type === 'image');
  if (BUSINESS_PLAN_STEPS.some((step) => step.key === draft.active)
    && (draft.active !== 'supplement' || hasSupplement)) return draft.active;
  if (draft.finalPlan) return 'done';
  if (draft.plan) return 'preview';
  if (hasSupplement) return 'supplement';
  return draft.refinedDone ? 'setup' : 'refine';
}
