import assert from 'node:assert/strict';
import test from 'node:test';
import { BUSINESS_PLAN_STEPS, getBusinessPlanResumeStep } from '../src/businessPlanFlow.js';

const supplementDraft = {
  refinedDone: true,
  templateInfo: { fields: ['시장 분석'] },
  fieldAnalysis: [{ field_id: 'market', status: 'missing' }],
  supplementAnswers: { 'market:시장 규모': '100억원' },
  supplementPage: 2,
};

test('saved stages resume at the same stage', () => {
  for (const { key } of BUSINESS_PLAN_STEPS) {
    assert.equal(getBusinessPlanResumeStep({ ...supplementDraft, active: key }), key);
  }
});

test('existing supplement drafts resume without uploading or analyzing the template again', () => {
  const draft = JSON.parse(JSON.stringify(supplementDraft));
  assert.equal(getBusinessPlanResumeStep(draft), 'supplement');
  assert.equal(draft.supplementPage, 2);
  assert.equal(draft.supplementAnswers['market:시장 규모'], '100억원');
});

test('older drafts resume from their saved results', () => {
  assert.equal(getBusinessPlanResumeStep({}), 'refine');
  assert.equal(getBusinessPlanResumeStep({ refinedDone: true }), 'setup');
  assert.equal(getBusinessPlanResumeStep({ ...supplementDraft, plan: { sections: [] } }), 'preview');
  assert.equal(getBusinessPlanResumeStep({ finalPlan: { sections: [] } }), 'done');
});

test('invalid or hidden saved stages use the available draft stage', () => {
  assert.equal(getBusinessPlanResumeStep({ ...supplementDraft, active: 'unknown' }), 'supplement');
  assert.equal(getBusinessPlanResumeStep({ active: 'supplement', refinedDone: true }), 'setup');
  assert.equal(getBusinessPlanResumeStep({ ...supplementDraft, active: 'supplement',
    fieldAnalysis: [{ status: 'ready' }], plan: { sections: [] } }), 'preview');
});
