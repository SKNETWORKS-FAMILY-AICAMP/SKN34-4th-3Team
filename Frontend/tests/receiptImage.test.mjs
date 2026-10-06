import assert from 'node:assert/strict';
import test from 'node:test';
import { fitWithin } from '../src/receiptImage.js';

test('긴 변이 2000px를 넘으면 비율을 지켜 줄인다', () => {
  assert.deepEqual(fitWithin(4000, 3000), { width: 2000, height: 1500 });
  assert.deepEqual(fitWithin(3024, 4032), { width: 1500, height: 2000 });
});

test('2000px 이하면 그대로 둔다', () => {
  assert.deepEqual(fitWithin(2000, 1000), { width: 2000, height: 1000 });
  assert.deepEqual(fitWithin(800, 600), { width: 800, height: 600 });
});

test('줄인 크기는 정수로 반올림한다', () => {
  assert.deepEqual(fitWithin(3001, 2001), { width: 2000, height: 1334 });
});
