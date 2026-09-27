import assert from 'node:assert/strict';
import test from 'node:test';
import { paginateSupplementFields, reassessSupplementFields, templateContext } from '../src/businessPlanSupplement.js';

const makeField = (id, section, type = 'multiline_text', missing = ['기간']) => ({
  field_id: id, section_id: section, type, status: 'missing', missing_fields: missing,
  required_information: missing, instruction: id, mapped_information: [],
});

test('related fields share a page and large fields stay whole', () => {
  const fields = [
    makeField('development', '2-1'), makeField('schedule', '2-1', 'table'),
    makeField('leader', '4-1', 'multiline_text', ['경력', '프로젝트', '역량']),
    makeField('team', '4-1'), makeField('overseas', '3-2'),
  ];
  const pages = paginateSupplementFields(fields, 560);
  assert.deepEqual(pages[0].map((field) => field.field_id), ['development', 'schedule']);
  assert.ok(pages.length > 1);
  assert.equal(pages.flat().length, fields.length);
});

test('answers survive page changes and statuses distinguish missing from not applicable', () => {
  const fields = [makeField('schedule', '2-1', 'table'), makeField('overseas', '3-2')];
  const answers = { 'schedule:기간': '2026년 10월 ~ 12월' };
  const choices = { overseas: 'not_applicable' };
  const firstPage = paginateSupplementFields(fields)[0];
  assert.equal(firstPage[0].field_id, 'schedule');
  const updated = reassessSupplementFields(fields, answers, choices);
  assert.deepEqual(updated.map((field) => field.status), ['ready', 'not_applicable']);
  assert.equal(answers['schedule:기간'], '2026년 10월 ~ 12월');
  const context = JSON.parse(templateContext(updated, answers, choices).split('\n', 2)[1]);
  assert.equal(context.fields[0].answers['기간'], '2026년 10월 ~ 12월');
  assert.equal(context.fields[1].status, 'not_applicable');
});

test('explicit lack of information remains missing and does not send stale answers', () => {
  const fields = [makeField('schedule', '2-1')];
  const answers = { 'schedule:기간': '이전에 입력한 기간' };
  const choices = { schedule: 'no_information' };
  assert.equal(reassessSupplementFields(fields, answers, choices)[0].status, 'missing');
  const context = JSON.parse(templateContext(fields, answers, choices).split('\n', 2)[1]);
  assert.equal(context.fields[0].answers['기간'], '');
});

test('supplement answer reaches the matching template field after its missing label is cleared', () => {
  const field = makeField('section_7', '4-1', 'multiline_text',
    ['대표자·팀원의 보유역량 / 기술보호 노력']);
  field.required_information = ['대표자 경력', '팀원 역량'];
  const answers = {
    'section_7:대표자·팀원의 보유역량 / 기술보호 노력': '대표자가 개발을 맡고 기술 문서를 접근 권한으로 보호한다.',
  };
  const updated = reassessSupplementFields([field], answers, {});
  assert.equal(updated[0].status, 'ready');
  assert.deepEqual(updated[0].missing_fields, []);
  const context = JSON.parse(templateContext(updated, answers).split('\n', 2)[1]);
  assert.equal(context.fields[0].answers['대표자·팀원의 보유역량 / 기술보호 노력'],
    answers['section_7:대표자·팀원의 보유역량 / 기술보호 노력']);
  const noInformation = JSON.parse(templateContext(updated, answers,
    { section_7: 'no_information' }).split('\n', 2)[1]);
  assert.equal(noInformation.fields[0].answers['대표자·팀원의 보유역량 / 기술보호 노력'], '');
});

test('an image field becomes ready only when its file is attached', () => {
  const field = makeField('photo', 'overview', 'image', ['이미지 파일']);
  assert.equal(reassessSupplementFields([field], {}, {}, {})[0].status, 'missing');
  const image = { photo: { mimeType: 'image/png', contentBase64: 'abc' } };
  const ready = reassessSupplementFields([field], {}, {}, image);
  assert.equal(ready[0].status, 'ready');
  assert.equal(JSON.parse(templateContext(ready, {}, {}).split('\n', 2)[1]).fields[0].type, 'image');
  assert.equal(reassessSupplementFields(ready, {}, {}, {})[0].status, 'missing');
  assert.equal(reassessSupplementFields([field], {}, { photo: 'not_applicable' }, image)[0].status,
    'not_applicable');
});
