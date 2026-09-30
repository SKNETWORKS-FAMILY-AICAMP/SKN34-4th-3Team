// 지출관리 엑셀 보고서. 요약 · 지출 내역 · 품목 상세 세 시트로 만든다.
// ExcelJS는 호출하는 쪽에서 넘긴다(화면에서는 눌렀을 때만 불러오고, 테스트에서는 바로 넘긴다).

const COLOR = {
  brand: 'FF2F63E0',
  brandSoft: 'FFE8EFFD',
  ink: 'FF15181F',
  muted: 'FF6B7280',
  line: 'FFD9DEE8',
  zebra: 'FFF7F9FC',
  totalFill: 'FFEEF2F8',
  white: 'FFFFFFFF',
};

// 판정 순서·색. 화면의 인정/확인 필요/불인정 태그와 같은 이름을 쓴다.
export const TIER_META = {
  high: { label: '인정', fill: 'FFE3F5EA', font: 'FF1E7A46' },
  ambiguous: { label: '확인 필요', fill: 'FFFFF3D6', font: 'FF9A6200' },
  low: { label: '불인정', fill: 'FFFDE4E4', font: 'FFB42318' },
};
const TIER_ORDER = ['high', 'ambiguous', 'low'];

const WON = '#,##0"원"';
const COUNT = '#,##0"건"';
const PCT = '0.0%';
const FONT = 'Malgun Gothic';

const thin = { style: 'thin', color: { argb: COLOR.line } };
const BOX = { top: thin, left: thin, bottom: thin, right: thin };

const amountOf = (it) => Number(it.amount) || 0;
const tierOf = (it) => (TIER_META[it.tier] ? it.tier : 'ambiguous');

// 엑셀 셀에 쓰는 날짜는 UTC 기준으로 저장된다. 로컬 자정으로 만들면 한국 시간에서는
// 전날 15시로 저장돼 하루 앞당겨 보이므로, 날짜는 UTC 자정으로 만들고 UTC 값으로 읽는다.
// "2026-08-01" → 2026-08-01T00:00Z. 형식이 다르면 null.
export function parseTxDate(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value || ''));
  return m ? new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]))) : null;
}

const pad2 = (n) => String(n).padStart(2, '0');
const utcYmd = (d) => `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`;
const localYmd = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;

// 업로드 시각(서버 UTC)을 브라우저 현지 시각 그대로 엑셀에 보이도록 옮긴다.
export function toSheetLocalTime(value) {
  const d = value ? new Date(value) : null;
  if (!d || Number.isNaN(d.getTime())) return '';
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000);
}

// 영수증을 거래일 오름차순으로(거래일이 없는 건은 맨 뒤) 정렬한다.
export function sortByTxDate(items) {
  return [...items].sort((a, b) => {
    const da = parseTxDate(a.date);
    const db = parseTxDate(b.date);
    if (da && db) return da - db || a.expenseId - b.expenseId;
    if (da) return -1;
    if (db) return 1;
    return a.expenseId - b.expenseId;
  });
}

// 요약 시트에 들어갈 숫자를 한 번에 계산한다.
export function summarize(items) {
  const total = items.reduce((s, it) => s + amountOf(it), 0);
  const byTier = Object.fromEntries(TIER_ORDER.map((t) => [t, { count: 0, amount: 0 }]));
  const byCategory = new Map();
  const byMonth = new Map();
  items.forEach((it) => {
    const amount = amountOf(it);
    const tier = tierOf(it);
    byTier[tier].count += 1;
    byTier[tier].amount += amount;

    const cat = it.category || '기타';
    const c = byCategory.get(cat) || { count: 0, amount: 0, high: 0, ambiguous: 0, low: 0 };
    c.count += 1;
    c.amount += amount;
    c[tier] += amount;
    byCategory.set(cat, c);

    const d = parseTxDate(it.date);
    const month = d ? `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}` : '거래일 미상';
    const mo = byMonth.get(month) || { count: 0, amount: 0, high: 0 };
    mo.count += 1;
    mo.amount += amount;
    if (tier === 'high') mo.high += amount;
    byMonth.set(month, mo);
  });
  const dates = items.map((it) => parseTxDate(it.date)).filter(Boolean).sort((a, b) => a - b);
  return {
    count: items.length,
    total,
    byTier,
    categories: [...byCategory.entries()].sort((a, b) => b[1].amount - a[1].amount),
    months: [...byMonth.entries()].sort(([a], [b]) => (a === '거래일 미상' ? 1 : b === '거래일 미상' ? -1 : a.localeCompare(b))),
    from: dates[0] || null,
    to: dates[dates.length - 1] || null,
  };
}

function styleHeader(row) {
  row.height = 24;
  row.eachCell((cell) => {
    cell.font = { name: FONT, bold: true, size: 10, color: { argb: COLOR.white } };
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: COLOR.brand } };
    cell.alignment = { vertical: 'middle', horizontal: 'center', wrapText: true };
    cell.border = BOX;
  });
}

function styleBody(row, zebra) {
  row.eachCell({ includeEmpty: true }, (cell) => {
    cell.font = { name: FONT, size: 10, color: { argb: COLOR.ink }, ...(cell.font && cell.font.bold ? { bold: true } : {}) };
    cell.border = BOX;
    cell.alignment = { vertical: 'middle', ...(cell.alignment || {}) };
    if (zebra) cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: COLOR.zebra } };
  });
}

function styleTotal(row) {
  row.height = 22;
  row.eachCell({ includeEmpty: true }, (cell) => {
    cell.font = { name: FONT, size: 10, bold: true, color: { argb: COLOR.ink } };
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: COLOR.totalFill } };
    cell.border = { ...BOX, top: { style: 'medium', color: { argb: COLOR.brand } } };
    cell.alignment = { vertical: 'middle', ...(cell.alignment || {}) };
  });
}

function paintTier(cell, tier) {
  const meta = TIER_META[tier];
  cell.value = meta.label;
  cell.font = { name: FONT, size: 10, bold: true, color: { argb: meta.font } };
  cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: meta.fill } };
  cell.alignment = { vertical: 'middle', horizontal: 'center' };
}

function sectionTitle(sheet, rowNo, text) {
  const cell = sheet.getCell(rowNo, 1);
  cell.value = text;
  cell.font = { name: FONT, size: 12, bold: true, color: { argb: COLOR.brand } };
  sheet.getRow(rowNo).height = 22;
}

// 표 하나(헤더 + 행 + 합계)를 startRow부터 쓰고, 다음에 쓸 행 번호를 돌려준다.
function writeTable(sheet, startRow, { headers, rows, total, formats }) {
  const header = sheet.getRow(startRow);
  headers.forEach((h, i) => { header.getCell(i + 1).value = h; });
  styleHeader(header);
  let r = startRow + 1;
  rows.forEach((values, idx) => {
    const row = sheet.getRow(r);
    values.forEach((v, i) => {
      const cell = row.getCell(i + 1);
      cell.value = v;
      if (formats[i]) cell.numFmt = formats[i];
      if (i > 0) cell.alignment = { horizontal: 'right' };
    });
    styleBody(row, idx % 2 === 1);
    r += 1;
  });
  if (total) {
    const row = sheet.getRow(r);
    total.forEach((v, i) => {
      const cell = row.getCell(i + 1);
      cell.value = v;
      if (formats[i]) cell.numFmt = formats[i];
      if (i > 0) cell.alignment = { horizontal: 'right' };
    });
    styleTotal(row);
    r += 1;
  }
  return r + 1;
}

function buildSummarySheet(wb, items, opts, s) {
  const sheet = wb.addWorksheet('요약', {
    views: [{ showGridLines: false }],
    pageSetup: { orientation: 'portrait', fitToPage: true, fitToWidth: 1, fitToHeight: 0, paperSize: 9 },
  });
  sheet.columns = [{ width: 18 }, { width: 18 }, { width: 18 }, { width: 18 }, { width: 18 }, { width: 18 }];

  sheet.mergeCells('A1:F1');
  const title = sheet.getCell('A1');
  title.value = '지출 내역 보고서';
  title.font = { name: FONT, size: 18, bold: true, color: { argb: COLOR.ink } };
  sheet.getRow(1).height = 32;

  sheet.mergeCells('A2:F2');
  const period = s.from ? `${utcYmd(s.from)} ~ ${utcYmd(s.to)}` : '거래일 정보 없음';
  const meta = sheet.getCell('A2');
  meta.value = `거래 기간 ${period}   ·   작성일 ${localYmd(opts.now)}   ·   대상 ${opts.filterLabel || '전체'} ${s.count}건`;
  meta.font = { name: FONT, size: 10, color: { argb: COLOR.muted } };

  // 핵심 지표 4칸: 라벨 / 금액 / 건수
  const kpis = [
    { label: '총 지출', amount: s.total, count: s.count, color: COLOR.brand },
    ...TIER_ORDER.map((t) => ({ label: TIER_META[t].label, amount: s.byTier[t].amount, count: s.byTier[t].count, color: TIER_META[t].font })),
  ];
  kpis.forEach((k, i) => {
    const col = i + 1;
    const labelCell = sheet.getCell(4, col);
    const amountCell = sheet.getCell(5, col);
    const countCell = sheet.getCell(6, col);
    labelCell.value = k.label;
    labelCell.font = { name: FONT, size: 10, bold: true, color: { argb: COLOR.muted } };
    amountCell.value = k.amount;
    amountCell.numFmt = WON;
    amountCell.font = { name: FONT, size: 14, bold: true, color: { argb: k.color } };
    countCell.value = k.count;
    countCell.numFmt = COUNT;
    countCell.font = { name: FONT, size: 10, color: { argb: COLOR.muted } };
    [labelCell, amountCell, countCell].forEach((c) => {
      c.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: COLOR.brandSoft } };
      c.alignment = { vertical: 'middle', horizontal: 'left', indent: 1 };
    });
    labelCell.border = { top: { style: 'medium', color: { argb: k.color } } };
  });
  sheet.getRow(5).height = 26;

  const pct = (v) => (s.total ? v / s.total : 0);
  let r = 8;
  sectionTitle(sheet, r, '판정별 합계');
  const tierStart = r + 2;
  r = writeTable(sheet, r + 1, {
    headers: ['판정', '건수', '금액', '금액 비중'],
    rows: TIER_ORDER.map((t) => [TIER_META[t].label, s.byTier[t].count, s.byTier[t].amount, pct(s.byTier[t].amount)]),
    total: ['합계', s.count, s.total, s.total ? 1 : 0],
    formats: [null, COUNT, WON, PCT],
  });
  // 판정 이름 칸에 화면과 같은 색을 입힌다.
  TIER_ORDER.forEach((t, i) => paintTier(sheet.getCell(tierStart + i, 1), t));

  sectionTitle(sheet, r, '지출항목별 합계');
  r = writeTable(sheet, r + 1, {
    headers: ['지출항목', '건수', '금액', '금액 비중', '인정 금액', '확인 필요·불인정'],
    rows: s.categories.map(([cat, c]) => [cat, c.count, c.amount, pct(c.amount), c.high, c.ambiguous + c.low]),
    total: ['합계', s.count, s.total, s.total ? 1 : 0, s.byTier.high.amount, s.byTier.ambiguous.amount + s.byTier.low.amount],
    formats: [null, COUNT, WON, PCT, WON, WON],
  });

  sectionTitle(sheet, r, '월별 합계');
  r = writeTable(sheet, r + 1, {
    headers: ['월', '건수', '금액', '인정 금액'],
    rows: s.months.map(([m, v]) => [m, v.count, v.amount, v.high]),
    total: ['합계', s.count, s.total, s.byTier.high.amount],
    formats: [null, COUNT, WON, WON],
  });

  sheet.mergeCells(r, 1, r, 6);
  const note = sheet.getCell(r, 1);
  note.value = '※ 경비 인정 판정은 영수증 인식 결과와 세법 규칙에 따른 참고용입니다. 신고 전에 세무 전문가와 확인하세요.';
  note.font = { name: FONT, size: 9, italic: true, color: { argb: COLOR.muted } };
  note.alignment = { wrapText: true, vertical: 'top' };
  sheet.getRow(r).height = 28;
}

function buildListSheet(wb, items, opts) {
  const sheet = wb.addWorksheet('지출 내역', {
    views: [{ state: 'frozen', ySplit: 1, showGridLines: false }],
    pageSetup: { orientation: 'landscape', fitToPage: true, fitToWidth: 1, fitToHeight: 0, paperSize: 9, printTitlesRow: '1:1' },
  });
  sheet.columns = [
    { header: 'No', key: 'no', width: 6 },
    { header: '거래일', key: 'date', width: 12 },
    { header: '상호', key: 'vendor', width: 24 },
    { header: '지출항목', key: 'category', width: 12 },
    { header: '금액', key: 'amount', width: 14 },
    { header: '경비 판정', key: 'tier', width: 11 },
    { header: '증빙 유형', key: 'proof', width: 16 },
    { header: '증빙 적격', key: 'proofValid', width: 10 },
    { header: '확인할 점', key: 'reason', width: 34 },
    { header: '품목', key: 'items', width: 40 },
    { header: '업로드일', key: 'uploadedAt', width: 17 },
  ];
  styleHeader(sheet.getRow(1));

  items.forEach((it, i) => {
    const goods = (it.items || []).map((g) => (g.price != null ? `${g.name} (${Number(g.price).toLocaleString()}원)` : g.name));
    const row = sheet.addRow({
      no: i + 1,
      date: parseTxDate(it.date) || '미상',
      vendor: it.vendor || '상호 미상',
      category: it.category,
      amount: amountOf(it),
      tier: '',
      proof: it.proofTypeLabel || '',
      proofValid: it.proofValid === true ? '적격' : it.proofValid === false ? '부적격' : '확인 필요',
      reason: opts.reasonOf ? opts.reasonOf(it) || '-' : '-',
      items: goods.join('\n') || '-',
      uploadedAt: toSheetLocalTime(it.uploadedAt),
    });
    styleBody(row, i % 2 === 1);
    row.getCell('no').alignment = { vertical: 'middle', horizontal: 'center' };
    row.getCell('date').numFmt = 'yyyy-mm-dd';
    row.getCell('date').alignment = { vertical: 'middle', horizontal: 'center' };
    row.getCell('amount').numFmt = WON;
    row.getCell('uploadedAt').numFmt = 'yyyy-mm-dd hh:mm';
    row.getCell('proofValid').alignment = { vertical: 'middle', horizontal: 'center' };
    row.getCell('reason').alignment = { vertical: 'middle', wrapText: true };
    row.getCell('items').alignment = { vertical: 'middle', wrapText: true };
    if (it.proofValid === false) row.getCell('proofValid').font = { name: FONT, size: 10, bold: true, color: { argb: TIER_META.low.font } };
    if (!it.vendor || it.vendor === '상호 미상') row.getCell('vendor').font = { name: FONT, size: 10, color: { argb: COLOR.muted } };
    paintTier(row.getCell('tier'), tierOf(it));
    row.height = Math.max(20, Math.max(goods.length, 1) * 15 + 6);
  });

  const last = items.length + 1;
  const total = sheet.addRow({
    no: '',
    date: '',
    vendor: `합계 ${items.length}건`,
    amount: items.length ? { formula: `SUM(E2:E${last})`, result: items.reduce((s, it) => s + amountOf(it), 0) } : 0,
  });
  total.getCell('amount').numFmt = WON;
  styleTotal(total);
  if (items.length) sheet.autoFilter = { from: 'A1', to: `K${last}` };
}

function buildItemsSheet(wb, items) {
  const sheet = wb.addWorksheet('품목 상세', {
    views: [{ state: 'frozen', ySplit: 1, showGridLines: false }],
    pageSetup: { orientation: 'portrait', fitToPage: true, fitToWidth: 1, fitToHeight: 0, paperSize: 9, printTitlesRow: '1:1' },
  });
  sheet.columns = [
    { header: '영수증 No', key: 'no', width: 10 },
    { header: '거래일', key: 'date', width: 12 },
    { header: '상호', key: 'vendor', width: 24 },
    { header: '지출항목', key: 'category', width: 12 },
    { header: '품목', key: 'name', width: 34 },
    { header: '금액', key: 'price', width: 14 },
  ];
  styleHeader(sheet.getRow(1));
  let count = 0;
  let sum = 0;
  items.forEach((it, i) => {
    (it.items || []).forEach((g) => {
      const row = sheet.addRow({
        no: i + 1,
        date: parseTxDate(it.date) || '미상',
        vendor: it.vendor || '상호 미상',
        category: it.category,
        name: g.name,
        price: g.price != null ? Number(g.price) : '-',
      });
      // 같은 영수증의 품목은 같은 줄무늬로 묶어 보이게 한다.
      styleBody(row, i % 2 === 1);
      row.getCell('no').alignment = { vertical: 'middle', horizontal: 'center' };
      row.getCell('date').numFmt = 'yyyy-mm-dd';
      row.getCell('date').alignment = { vertical: 'middle', horizontal: 'center' };
      row.getCell('price').numFmt = WON;
      row.getCell('price').alignment = { vertical: 'middle', horizontal: 'right' };
      count += 1;
      if (g.price != null) sum += Number(g.price) || 0;
    });
  });
  if (!count) {
    const row = sheet.addRow({ vendor: '인식된 품목이 없습니다.' });
    styleBody(row, false);
    return;
  }
  const total = sheet.addRow({ vendor: `합계 ${count}개 품목`, price: { formula: `SUM(F2:F${count + 1})`, result: sum } });
  total.getCell('price').numFmt = WON;
  styleTotal(total);
  sheet.autoFilter = { from: 'A1', to: `F${count + 1}` };
}

// 워크북을 만들어 돌려준다. opts: { now: Date, filterLabel: '전체' | '인정' …, reasonOf: (item) => string }
export function buildExpensesWorkbook(ExcelJS, rawItems, opts = {}) {
  const options = { now: new Date(), ...opts };
  const items = sortByTxDate(rawItems);
  const wb = new ExcelJS.Workbook();
  wb.creator = '창업ON';
  wb.created = options.now;
  buildSummarySheet(wb, items, options, summarize(items));
  buildListSheet(wb, items, options);
  buildItemsSheet(wb, items);
  return wb;
}
