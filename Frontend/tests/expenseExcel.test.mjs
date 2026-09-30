import assert from 'node:assert/strict';
import test from 'node:test';
import ExcelJS from 'exceljs';
import { buildExpensesWorkbook, sortByTxDate, summarize } from '../src/expenseExcel.js';

const items = [
  { expenseId: 3, vendor: 'CU', category: '복리후생비', amount: 12000, date: '2026-09-03', tier: 'ambiguous',
    proofTypeLabel: '신용카드 매출전표', proofValid: true, missingFields: [], items: [{ name: '생수', price: 2000 }, { name: '커피', price: 10000 }] },
  { expenseId: 1, vendor: '상호 미상', category: '사무용품', amount: 30000, date: '2026-08-20', tier: 'high',
    proofTypeLabel: '세금계산서', proofValid: true, missingFields: ['상호'], items: [] },
  { expenseId: 2, vendor: '식당', category: '접대비', amount: 45000, date: null, tier: 'low',
    proofTypeLabel: '간이영수증', proofValid: false, missingFields: ['거래일'], items: [{ name: '식사', price: null }] },
];

test('거래일 오름차순, 거래일 없는 건은 맨 뒤', () => {
  assert.deepEqual(sortByTxDate(items).map((it) => it.expenseId), [1, 3, 2]);
});

test('요약: 판정별·지출항목별·월별 합계', () => {
  const s = summarize(items);
  assert.equal(s.total, 87000);
  assert.deepEqual(s.byTier.high, { count: 1, amount: 30000 });
  assert.deepEqual(s.byTier.low, { count: 1, amount: 45000 });
  assert.equal(s.categories[0][0], '접대비');
  assert.deepEqual(s.months.map(([m]) => m), ['2026-08', '2026-09', '거래일 미상']);
});

test('워크북: 세 시트와 합계, 판정 표시', async () => {
  const wb = buildExpensesWorkbook(ExcelJS, items, {
    now: new Date(2026, 8, 30), filterLabel: '전체', reasonOf: (it) => (it.missingFields.length ? '확인 필요' : ''),
  });
  assert.deepEqual(wb.worksheets.map((ws) => ws.name), ['요약', '지출 내역', '품목 상세']);

  // 파일로 썼다가 다시 읽어도 깨지지 않아야 한다.
  const again = new ExcelJS.Workbook();
  await again.xlsx.load(await wb.xlsx.writeBuffer());

  const list = again.getWorksheet('지출 내역');
  assert.equal(list.getCell('C2').value, '상호 미상');
  // 한국 시간에서도 거래일이 하루 앞당겨지지 않아야 한다(엑셀 날짜는 UTC로 저장된다).
  assert.equal(list.getCell('B2').value.toISOString(), '2026-08-20T00:00:00.000Z');
  assert.equal(list.getCell('F2').value, '인정');
  assert.equal(list.getCell('F4').value, '불인정');
  assert.equal(list.getCell('B4').value, '미상');
  assert.equal(list.getCell('H4').value, '부적격');
  assert.equal(list.getCell('J3').value, '생수 (2,000원)\n커피 (10,000원)');
  assert.equal(list.getCell('E5').value.formula, 'SUM(E2:E4)');

  const summary = again.getWorksheet('요약');
  assert.match(summary.getCell('A2').value, /2026-08-20 ~ 2026-09-03/);
  assert.equal(summary.getCell('B5').value, 30000);

  const goods = again.getWorksheet('품목 상세');
  assert.equal(goods.rowCount, 5); // 헤더 + 품목 3 + 합계
  assert.equal(goods.getCell('F5').value.formula, 'SUM(F2:F4)');
});

test('빈 목록도 파일을 만든다', async () => {
  const wb = buildExpensesWorkbook(ExcelJS, [], { now: new Date(2026, 8, 30) });
  const buf = await wb.xlsx.writeBuffer();
  assert.ok(buf.byteLength > 0);
});
