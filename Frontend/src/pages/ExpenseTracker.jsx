import React, { useState, useEffect } from 'react';
import { api } from '../api.js';
import { linkBtn } from '../utils.js';

const EXCEL_HEADERS = [
  { header: '업로드일', key: 'uploadedAt', width: 20 },
  { header: '거래일', key: 'date', width: 13 },
  { header: '상호', key: 'vendor', width: 22 },
  { header: '지출항목', key: 'category', width: 12 },
  { header: '금액', key: 'amount', width: 12 },
  { header: '경비 인정 판정', key: 'tierLabel', width: 14 },
  { header: '증빙 유형', key: 'proofTypeLabel', width: 16 },
  { header: '증빙 적격', key: 'proofValidLabel', width: 10 },
  { header: '빠진 정보', key: 'missingFields', width: 26 },
  { header: '품목', key: 'items', width: 30 },
];

// 지금 화면에 있는 지출 목록을 그대로 .xlsx 파일로 만든다. 서버를 거치지 않고 브라우저에서 바로 만든다.
// exceljs는 용량이 커서 누르기 전까지 불러오지 않는다(정적 import면 이 페이지를 열기만 해도
// 전체 번들에 실려 모두가 받게 된다). 실제로 다운로드 버튼을 눌렀을 때만 그 조각을 받아온다.
async function downloadExpensesExcel(items) {
  const { default: ExcelJS } = await import('exceljs');
  const workbook = new ExcelJS.Workbook();
  workbook.creator = '창업ON';
  workbook.created = new Date();

  const sheet = workbook.addWorksheet('지출 내역');
  sheet.columns = EXCEL_HEADERS;
  sheet.getRow(1).font = { bold: true };
  sheet.getRow(1).alignment = { vertical: 'middle' };
  sheet.views = [{ state: 'frozen', ySplit: 1 }];

  items.forEach((it) => {
    sheet.addRow({
      uploadedAt: it.uploadedAt ? new Date(it.uploadedAt) : null,
      date: it.date,
      vendor: it.vendor,
      category: it.category,
      amount: it.amount,
      tierLabel: it.tierLabel,
      proofTypeLabel: it.proofTypeLabel,
      proofValidLabel: it.proofValid === true ? '적격' : it.proofValid === false ? '부적격' : '확인 필요',
      missingFields: (it.missingFields || []).join(', '),
      items: (it.items || []).map((i) => (i.price != null ? `${i.name}(${i.price.toLocaleString()}원)` : i.name)).join(', '),
    });
  });

  const amountCol = sheet.getColumn('amount');
  amountCol.numFmt = '#,##0"원"';
  const uploadedCol = sheet.getColumn('uploadedAt');
  uploadedCol.numFmt = 'yyyy-mm-dd hh:mm';

  const total = items.reduce((s, x) => s + x.amount, 0);
  const totalRow = sheet.addRow({ vendor: '합계', amount: total });
  totalRow.font = { bold: true };
  totalRow.getCell('amount').numFmt = '#,##0"원"';

  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const today = new Date().toISOString().slice(0, 10);
  a.href = url;
  a.download = `지출내역_${today}.xlsx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/* ===== 지출관리: 영수증 업로드 → OCR → 경비 인정 판정 ===== */

// 인식 중에 보여줄 단계. 실제 진행 신호는 없어(요청 하나로 끝남) 시간 흐름으로 단계를 넘긴다.
const ANALYZE_STEPS = ['영수증 글자 읽기', '금액·상호·증빙 정리', '경비 인정 가능성 판단'];

const EXP_JUDGE_CATS = ['사무용품', '통신비', '차량유지비', '광고선전비', '임차료', '복리후생비', '접대비', '교육·도서', '기타'];
// 목록 카드는 폭이 좁아 서버가 주는 긴 tierLabel 대신 짧은 표기를 쓴다.
const TIER_SHORT_LABELS = { high: '높음', ambiguous: '확인 필요', low: '어려움' };
// 카드의 상태 태그(경비 인정/확인 필요/어려움)에 쓰는 문구.
const TIER_TAG_TEXT = { high: '경비 인정', ambiguous: '경비 확인 필요', low: '경비 인정 어려움' };
// 카드 상태 태그 색상 + 필터 탭에 쓰는 클래스. high=인정 / ambiguous=확인 필요 / low=불인정.
const TIER_CLASS = { high: 'ok', ambiguous: 'check', low: 'bad' };
const TIER_TABS = [
  { key: 'all', label: '전체' },
  { key: 'high', label: '인정' },
  { key: 'ambiguous', label: '확인 필요' },
  { key: 'low', label: '불인정' },
];

// 서버는 UTC 시각을 주므로 브라우저 현지 시각(한국이면 KST)으로 바꿔 "9월 20일 오후 9:39"처럼 보여준다.
function formatUploadedAt(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const sameYear = d.getFullYear() === new Date().getFullYear();
  return d.toLocaleString('ko-KR', {
    ...(sameYear ? {} : { year: 'numeric' }),
    month: 'long',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

const STEP_ICONS = { pass: '✔', warn: '!', fail: '✖', unknown: '?' };

// 길어지기 쉬운 상세 내용을 제목 줄만 남기고 접었다 펼 수 있게 한다.
// open/onToggle을 주면(제어 모드) 펼침 상태를 부모가 들고 있어, 카드를 접었다 펴도
// "이렇게 판단했어요" 같은 펼친 상태가 초기화되지 않고 그대로 유지된다.
function Fold({ title, hint, defaultOpen = false, open: openProp, onToggle, children }) {
  const [openState, setOpenState] = useState(defaultOpen);
  const controlled = openProp !== undefined;
  const open = controlled ? openProp : openState;
  const toggle = () => (controlled ? onToggle && onToggle(!open) : setOpenState((v) => !v));
  return (
    <section className={'exp-fold' + (open ? ' is-open' : '')}>
      <button type="button" className="exp-fold__head" onClick={toggle} aria-expanded={open}>
        <span className="exp-fold__ttl">{title}</span>
        {hint && <span className="exp-fold__hint">{hint}</span>}
        <span className="exp-fold__chev" aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>
      {open && <div className="exp-fold__body">{children}</div>}
    </section>
  );
}

// 필드 하나의 읽음 상태. 여러 필드를 합칠 때도 재사용한다.
function fieldState(f) {
  return f.read === false ? 'miss' : f.read ? 'ok' : 'unk';
}
// 여러 필드를 하나의 줄로 합칠 때: 하나라도 못 읽었으면 miss, 전부 읽었으면 ok, 그 외 unk.
function comboState(fields) {
  if (fields.some((f) => f.read === false)) return 'miss';
  if (fields.every((f) => f.read)) return 'ok';
  return 'unk';
}
const STATE_MARK = { miss: '✖', ok: '✔', unk: '?' };

// 영수증에서 읽은 항목(원문 인용 포함). 못 읽은 항목은 빨간색으로 드러낸다.
// 상호·거래일은 한 줄로(상호는 수정 가능), 품목·금액은 표로 묶어서 보여준다.
function ReceiptFields({ analysis, expenseId, onUpdated }) {
  const [addOpen, setAddOpen] = useState(false);
  const [itemNameDraft, setItemNameDraft] = useState('');
  const [itemPriceDraft, setItemPriceDraft] = useState('');
  const [addBusy, setAddBusy] = useState(false);
  const [addErr, setAddErr] = useState('');
  const [delBusyIndex, setDelBusyIndex] = useState(-1);
  const [delErr, setDelErr] = useState('');

  const [vendorOpen, setVendorOpen] = useState(false);
  const [vendorDraft, setVendorDraft] = useState('');
  const [vendorBusy, setVendorBusy] = useState(false);
  const [vendorErr, setVendorErr] = useState('');

  const byKey = {};
  analysis.fields.forEach((f) => { byKey[f.key] = f; });
  const vendorField = byKey.vendor;
  const dateField = byKey.date;
  const amountField = byKey.amount;
  const restFields = analysis.fields.filter((f) => !['vendor', 'date', 'amount', 'items'].includes(f.key));
  const items = analysis.items || [];

  const openVendorEdit = () => {
    setVendorDraft((vendorField && vendorField.value) || '');
    setVendorErr('');
    setVendorOpen(true);
  };
  const submitVendor = async (e) => {
    e.preventDefault();
    const text = vendorDraft.trim();
    if (!text || vendorBusy || !expenseId) return;
    setVendorBusy(true);
    setVendorErr('');
    try {
      const updated = await api.updateExpenseVendor(expenseId, text);
      onUpdated && onUpdated(updated);
      setVendorOpen(false);
    } catch (e2) {
      setVendorErr('상호를 저장하지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setVendorBusy(false);
    }
  };

  const submitItem = async (e) => {
    e.preventDefault();
    const name = itemNameDraft.trim();
    if (!name || addBusy || !expenseId) return;
    const priceNum = itemPriceDraft.trim() ? Number(itemPriceDraft.trim().replace(/[^0-9]/g, '')) : null;
    setAddBusy(true);
    setAddErr('');
    try {
      const updated = await api.addExpenseItem(expenseId, name, priceNum);
      onUpdated && onUpdated(updated);
      setItemNameDraft('');
      setItemPriceDraft('');
      setAddOpen(false);
    } catch (e2) {
      setAddErr('품목을 추가하지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setAddBusy(false);
    }
  };

  const deleteItem = async (index) => {
    if (delBusyIndex >= 0 || !expenseId) return;
    setDelBusyIndex(index);
    setDelErr('');
    try {
      const updated = await api.deleteExpenseItem(expenseId, index);
      onUpdated && onUpdated(updated);
    } catch (e2) {
      setDelErr('품목을 지우지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setDelBusyIndex(-1);
    }
  };

  return (
    <React.Fragment>
      {analysis.ocrSource === 'mock' && (
        <p className="cal__err">사진을 읽지 못해 아래는 실제 영수증 값이 아닌 샘플이에요. 다시 올려 주세요.</p>
      )}
      {analysis.ocrSource === 'ocr_llm' && (
        <p className="exp-ana__method">
          <b>OCR + LLM</b> · OCR이 글자를 읽고 LLM이 그 글자를 정리했어요
          {analysis.ocrConfidence != null && ` · OCR 인식 신뢰도 ${Math.round(analysis.ocrConfidence)}%`}
        </p>
      )}
      {analysis.ocrSource === 'vision' && (
        <p className="exp-ana__method"><b>Vision LLM</b> · OCR을 쓰지 못해 LLM이 이미지를 직접 읽었어요</p>
      )}
      <ul className="exp-ana__fields">
        {vendorField && dateField && (
          <li className={'exp-ana__field is-' + comboState([vendorField, dateField])}>
            <span className="exp-ana__mark" aria-hidden="true">{STATE_MARK[comboState([vendorField, dateField])]}</span>
            <span className="exp-ana__lbl">상호 · 거래일</span>
            {vendorOpen ? (
              <form className="exp-ana__val exp-ana__vendorform" onSubmit={submitVendor}>
                <input
                  type="text"
                  value={vendorDraft}
                  onChange={(e) => setVendorDraft(e.target.value)}
                  placeholder="상호 입력"
                  aria-label="상호 수정"
                  autoFocus
                  disabled={vendorBusy}
                />
                <button type="submit" disabled={vendorBusy || !vendorDraft.trim()}>저장</button>
                <button type="button" onClick={() => setVendorOpen(false)} disabled={vendorBusy}>취소</button>
                {vendorErr && <p className="cal__err">{vendorErr}</p>}
              </form>
            ) : (
              <span className="exp-ana__val">
                {vendorField.value || '상호 인식 못 함'} · {dateField.value || '거래일 인식 못 함'}
                {expenseId && (
                  <button type="button" className="exp-ana__editbtn" onClick={openVendorEdit}>✏️ 상호 수정</button>
                )}
              </span>
            )}
            {(vendorField.evidence || dateField.evidence) && (
              <span className="exp-ana__quote" title="영수증에 인쇄된 원문">
                영수증 원문 “{[vendorField.evidence, dateField.evidence].filter(Boolean).join(' / ')}”
              </span>
            )}
          </li>
        )}

        {amountField && (
          <li className={'exp-ana__field exp-ana__field--items is-' + fieldState(amountField)}>
            <span className="exp-ana__mark" aria-hidden="true">{STATE_MARK[fieldState(amountField)]}</span>
            <span className="exp-ana__lbl">품목 · 금액</span>
            <div className="exp-ana__val">
              {items.length > 0 ? (
                <table className="exp-ana__itemtable">
                  <thead>
                    <tr><th>품목</th><th>금액</th>{expenseId && <th className="exp-ana__itemtable-delcol" aria-hidden="true" />}</tr>
                  </thead>
                  <tbody>
                    {items.map((it, i) => (
                      <tr key={i}>
                        <td>{it.name}</td>
                        <td className="u-num">{it.price != null ? `${it.price.toLocaleString()}원` : '-'}</td>
                        {expenseId && (
                          <td className="exp-ana__itemtable-delcol">
                            <button
                              type="button"
                              className="exp-ana__itemdel"
                              onClick={() => deleteItem(i)}
                              disabled={delBusyIndex >= 0}
                              aria-label={`${it.name} 품목 삭제`}
                              title="품목 삭제"
                            >
                              {delBusyIndex === i ? '…' : '×'}
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <span>품목 인식 못 함</span>
              )}
              <div className="exp-ana__itemtotal">
                합계 <b>{amountField.value || '인식 못 함'}</b>
              </div>
              {delErr && <p className="cal__err">{delErr}</p>}
              {expenseId && (addOpen ? (
                <form className="exp-ana__itemform" onSubmit={submitItem}>
                  <input
                    type="text"
                    className="exp-ana__itemform-name"
                    value={itemNameDraft}
                    onChange={(e) => setItemNameDraft(e.target.value)}
                    placeholder="OCR이 놓친 품목명"
                    aria-label="빠진 품목명 입력"
                    autoFocus
                    disabled={addBusy}
                  />
                  <input
                    type="text"
                    inputMode="numeric"
                    className="exp-ana__itemform-price"
                    value={itemPriceDraft}
                    onChange={(e) => setItemPriceDraft(e.target.value)}
                    placeholder="금액(선택)"
                    aria-label="품목 금액 입력"
                    disabled={addBusy}
                  />
                  <button type="submit" className="exp-ana__itemform-submit" disabled={addBusy || !itemNameDraft.trim()} aria-label="품목 추가">
                    {addBusy ? '…' : '추가'}
                  </button>
                  <button
                    type="button"
                    className="exp-ana__itemform-cancel"
                    onClick={() => { setAddOpen(false); setItemNameDraft(''); setItemPriceDraft(''); setAddErr(''); }}
                    disabled={addBusy}
                    aria-label="품목 추가 취소"
                  >
                    취소
                  </button>
                </form>
              ) : (
                <button type="button" className="exp-ana__itemadd" onClick={() => setAddOpen(true)}>+ 품목 추가</button>
              ))}
              {addErr && <p className="cal__err">{addErr}</p>}
            </div>
          </li>
        )}

        {restFields.map((f) => {
          const state = fieldState(f);
          return (
            <li key={f.key} className={'exp-ana__field is-' + state}>
              <span className="exp-ana__mark" aria-hidden="true">{STATE_MARK[state]}</span>
              <span className="exp-ana__lbl">{f.label}</span>
              <span className="exp-ana__val">
                {f.value || '인식 못 함'}
                {state === 'unk' && <small> (기록 이전 영수증)</small>}
              </span>
              {f.evidence && (
                <span className="exp-ana__quote" title="영수증에 인쇄된 원문">
                  영수증 원문 “{f.evidence}”
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </React.Fragment>
  );
}

// 읽은 내용으로 판정에 이른 단계를 진행선으로 보여준다.
function ReceiptSteps({ analysis }) {
  return (
    <ol className="exp-ana__steps">
      {analysis.steps.map((st) => (
        <li key={st.key} className={'exp-ana__step is-' + st.result}>
          <span className="exp-ana__dot" aria-hidden="true">{STEP_ICONS[st.result] || '?'}</span>
          <div>
            <b>{st.title}</b>
            <p>{st.detail}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

// 지출항목과 증빙 상태에 맞는 관련 법령. 조문을 누르면 국가법령정보센터 원문으로 이동한다.
function LawList({ laws, note }) {
  return (
    <React.Fragment>
      {note && <p className="exp-law__note">{note}</p>}
      <ul className="exp-law">
        {laws.map((l) => (
          <li key={l.law + l.article} className="exp-law__item">
            <a href={l.url} target="_blank" rel="noreferrer">
              <b>{l.law} {l.article}</b>
              <span>{l.title}</span>
              {l.who && <em>{l.who}</em>}
              <i aria-hidden="true">↗</i>
            </a>
            <p>{l.point}</p>
          </li>
        ))}
      </ul>
      <p className="exp-law__disc">법령 요지는 이해를 돕기 위한 요약이에요. 정확한 내용은 원문과 세무사 확인이 필요해요.</p>
    </React.Fragment>
  );
}

// 카드를 펼치면 근거(RAG 출처 포함)를 그때 불러온다 — 목록 조회 때마다 매번 LLM을 부르지 않기 위해서다.
function ReceiptCard({ item, onDeleted, onCategoryChanged }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [imgUrl, setImgUrl] = useState(null);
  const [zoom, setZoom] = useState(false);
  const [analysis, setAnalysis] = useState(null); // 무엇을 읽고 어떻게 판단했는지 (LLM 없이 바로 온다)
  const [anaFailed, setAnaFailed] = useState(false);
  const [catBusy, setCatBusy] = useState(false);
  const [catErr, setCatErr] = useState('');
  const [catOpen, setCatOpen] = useState(false);
  // 카드를 접었다 펴도 "읽은 내용/판단/법령" 펼침 상태가 그대로 유지되도록 카드 레벨에서 들고 있는다.
  const [foldOpen, setFoldOpen] = useState({ read: false, judge: false, law: false });
  const catListRef = React.useRef(null);
  const catWrapRef = React.useRef(null);

  // 펼쳐진 목록 밖을 누르거나 Esc를 누르면 닫는다.
  useEffect(() => {
    if (!catOpen) return undefined;
    const onDown = (e) => {
      if (catWrapRef.current && !catWrapRef.current.contains(e.target)) setCatOpen(false);
    };
    const onKey = (e) => e.key === 'Escape' && setCatOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [catOpen]);

  // 열릴 때 현재 항목이 목록 안에서 보이도록 스크롤한다(페이지 스크롤은 건드리지 않는다).
  useEffect(() => {
    const box = catListRef.current;
    const on = box && box.querySelector('.is-on');
    if (catOpen && box && on) box.scrollTop = Math.max(0, on.offsetTop - box.clientHeight / 2 + on.offsetHeight / 2);
  }, [catOpen]);

  const loadAnalysis = () =>
    api
      .expenseAnalysis(item.expenseId)
      .then((a) => {
        setAnalysis(a);
        setAnaFailed(false);
      })
      .catch(() => setAnaFailed(true));

  useEffect(() => {
    if (!zoom) return undefined;
    const onKey = (e) => e.key === 'Escape' && setZoom(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [zoom]);

  // 목록에 뜨자마자 내가 올린 영수증이 맞는지 썸네일로 보여준다.
  useEffect(() => {
    let alive = true;
    let objUrl = null;
    api
      .receiptImage(item.receiptId)
      .then((blob) => {
        if (!alive) return;
        objUrl = URL.createObjectURL(blob);
        setImgUrl(objUrl);
      })
      .catch(() => {
        /* 원본이 없어도(예: 목업 응답) 목록은 그대로 보여준다 */
      });
    return () => {
      alive = false;
      if (objUrl) URL.revokeObjectURL(objUrl);
    };
  }, [item.receiptId]);

  const openDetail = async () => {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (!analysis) loadAnalysis();
    if (detail || busy) return;
    setBusy(true);
    setErr('');
    try {
      setDetail(await api.expenseDeductibility(item.expenseId));
    } catch (e) {
      setErr('근거를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setBusy(false);
    }
  };

  const changeCategory = async (category) => {
    setCatOpen(false);
    if (catBusy || category === item.category) return;
    setCatBusy(true);
    setCatErr('');
    try {
      const d = await api.updateExpenseCategory(item.expenseId, category);
      setDetail(d);
      loadAnalysis();
      onCategoryChanged(item.expenseId, category, d);
    } catch (e2) {
      setCatErr('지출항목을 바꾸지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setCatBusy(false);
    }
  };

  const remove = async () => {
    if (!window.confirm('이 영수증과 지출 기록을 삭제할까요?')) return;
    try {
      await api.deleteExpense(item.expenseId);
      onDeleted(item.expenseId);
    } catch (e) {
      setErr('삭제하지 못했어요. 잠시 후 다시 시도해 주세요.');
    }
  };

  const tierCls = TIER_CLASS[item.tier] || 'check';
  const uploadedLabel = formatUploadedAt(item.uploadedAt);

  return (
    <li className="exp-row">
      <div className="exp-row__main">
        <button
          type="button"
          className="exp-row__thumb"
          onClick={() => imgUrl && setZoom(true)}
          disabled={!imgUrl}
          aria-label="영수증 원본 크게 보기"
        >
          {imgUrl ? (
            <img src={imgUrl} alt={`${item.vendor} 영수증`} />
          ) : (
            <span className="exp-row__thumb-ph" aria-hidden="true">📄</span>
          )}
        </button>

        <div className="exp-row__body">
          <div className="exp-row__top">
            <span className="exp-row__vendor">{item.vendor}</span>
            <span className="u-num exp-row__amount">{item.amount.toLocaleString()}원</span>
          </div>

          <div className="exp-row__meta">
            {uploadedLabel && <span title="영수증을 올린 시각">{uploadedLabel} 업로드</span>}
            <span className="exp-row__dot" aria-hidden="true">·</span>
            <div className="exp-dd exp-dd--flat" ref={catWrapRef}>
              <button
                type="button"
                className={'exp-row__cat' + (catOpen ? ' is-open' : '')}
                onClick={() => setCatOpen((v) => !v)}
                disabled={catBusy}
                aria-haspopup="listbox"
                aria-expanded={catOpen}
                aria-label={`지출항목: ${item.category}. 눌러서 바꾸기`}
              >
                {item.category}
                <span className="exp-dd__chev" aria-hidden="true">{catOpen ? '▴' : '▾'}</span>
              </button>
              {catOpen && (
                <div className="exp-dd__list" role="listbox" aria-label="지출항목" ref={catListRef}>
                  {EXP_JUDGE_CATS.map((c) => (
                    <button
                      key={c}
                      type="button"
                      role="option"
                      aria-selected={item.category === c}
                      className={'exp-dd__opt' + (item.category === c ? ' is-on' : '')}
                      onClick={() => changeCategory(c)}
                    >
                      {c}
                      {item.category === c && <span aria-hidden="true">✔</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
          {catBusy && <p className="exp-card__busy" role="status">지출항목을 바꾸고 판정을 다시 계산하고 있어요…</p>}
          {catErr && <p className="cal__err">{catErr}</p>}

          <div className="exp-row__tags">
            <span className={'exp-row__tag exp-row__tag--' + tierCls}>
              {TIER_TAG_TEXT[item.tier] || item.tierLabel}
            </span>
            <span className="exp-row__tag">{item.proofTypeLabel}</span>
            {item.proofValid === false && <span className="exp-row__tag exp-row__tag--warn">증빙 부적격</span>}
            {item.proofValid === null && <span className="exp-row__tag exp-row__tag--warn">증빙 확인 필요</span>}
            {(item.missingFields || []).map((m) => (
              <span key={m} className="exp-row__tag exp-row__tag--warn">빠짐: {m}</span>
            ))}
          </div>

          <div className="exp-row__actions">
            <button type="button" className="exp-row__link" onClick={openDetail} aria-expanded={open}>
              {open ? '상세 접기' : '판독·판단·법령 상세보기'}
            </button>
            <span className="exp-row__sep" aria-hidden="true">|</span>
            <button type="button" className="exp-row__link exp-row__link--danger" onClick={remove}>삭제</button>
          </div>
        </div>
      </div>

      {zoom && imgUrl && (
        <div
          className="exp-lightbox"
          role="dialog"
          aria-modal="true"
          aria-label="영수증 원본"
          onClick={() => setZoom(false)}
        >
          <img src={imgUrl} alt={`${item.vendor} 영수증 원본`} onClick={(e) => e.stopPropagation()} />
          <button type="button" className="exp-lightbox__close" onClick={() => setZoom(false)} aria-label="닫기">
            ✕
          </button>
        </div>
      )}

      {open && (
        <div className="exp-card__detail">
          {anaFailed && <p className="cal__err">판독 내용을 불러오지 못했어요.</p>}
          {!analysis && !anaFailed && <p className="ai__hint">읽은 내용을 정리하고 있어요…</p>}
          {analysis && (
            <React.Fragment>
              <Fold
                title="📖 영수증에서 읽은 내용"
                hint={`${analysis.fields.filter((f) => f.read).length}/${analysis.fields.length}개 인식`}
                open={foldOpen.read}
                onToggle={(v) => setFoldOpen((f) => ({ ...f, read: v }))}
              >
                <ReceiptFields analysis={analysis} expenseId={item.expenseId} onUpdated={setAnalysis} />
              </Fold>
              <Fold
                title="🧭 이렇게 판단했어요"
                hint={`종합 ${TIER_SHORT_LABELS[analysis.tier] || analysis.tierLabel}`}
                open={foldOpen.judge}
                onToggle={(v) => setFoldOpen((f) => ({ ...f, judge: v }))}
              >
                <ReceiptSteps analysis={analysis} />
              </Fold>
              <Fold
                title="📚 세법 근거 · 관련 법령"
                hint={`법령 ${analysis.laws.length}건`}
                open={foldOpen.law}
                onToggle={(v) => setFoldOpen((f) => ({ ...f, law: v }))}
              >
                <LawList laws={analysis.laws} note={analysis.lawNote} />
                <h4 className="exp-ana__ttl">AI가 찾은 세법 자료</h4>
                {busy && <p className="ai__hint">관련 세법 자료를 찾고 있어요…</p>}
                {err && <p className="cal__err">{err}</p>}
                {detail && (
                  <React.Fragment>
                    <p style={{ margin: '0 0 8px' }}>{detail.basis}</p>
                    {detail.sources && detail.sources.length > 0 && (
                      <div className="msg-src">
                        <b>확인한 자료 {detail.sources.length}건</b>
                        {detail.sources.map((src, i) => <span key={i}>[{i + 1}] {src}</span>)}
                      </div>
                    )}
                  </React.Fragment>
                )}
              </Fold>
            </React.Fragment>
          )}
        </div>
      )}
    </li>
  );
}

export function ExpenseTracker({ user, onRequireLogin }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState('');
  const [uploadStep, setUploadStep] = useState(0);
  const [uploadIndex, setUploadIndex] = useState(0); // 여러 장을 올릴 때 지금 몇 번째인지
  const [uploadTotal, setUploadTotal] = useState(0);
  const [err, setErr] = useState('');
  const [tierFilter, setTierFilter] = useState('all');
  const [search, setSearch] = useState('');
  const fileRef = React.useRef(null);
  const userId = user && user.id;

  const load = () => {
    if (!userId) return;
    setLoading(true);
    api
      .expenses()
      // 방금 올린 영수증이 맨 위에 오도록 최신순으로 보여준다.
      .then((r) => setItems([...((r && r.expenses) || [])].sort((a, b) => b.expenseId - a.expenseId)))
      .catch(() => setErr('지출 목록을 불러오지 못했어요.'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const pickFile = () => fileRef.current && fileRef.current.click();

  // 한 번에 여러 장을 고를 수 있다. 한 장씩 순서대로 올려서(동시에 여러 OCR 요청을 던지지 않아)
  // 서버 부담을 줄이고, 실패한 파일만 따로 모아 끝나고 한 번에 알려준다.
  const onFile = async (e) => {
    const picked = Array.from(e.target.files || []);
    e.target.value = '';
    if (!picked.length) return;
    if (!userId) {
      onRequireLogin && onRequireLogin();
      return;
    }

    const valid = [];
    const rejected = [];
    picked.forEach((file) => {
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
        rejected.push(`${file.name} (JPEG·PNG·WebP만 가능)`);
      } else if (file.size > 4 * 1024 * 1024) {
        rejected.push(`${file.name} (4MB 초과)`);
      } else {
        valid.push(file);
      }
    });
    if (!valid.length) {
      setErr(rejected.length ? `올릴 수 있는 영수증이 없어요 — ${rejected.join(', ')}` : '');
      return;
    }

    setErr('');
    setUploading(true);
    setUploadTotal(valid.length);
    const failed = [...rejected];
    let stoppedByAuth = false;

    for (let i = 0; i < valid.length; i++) {
      setUploadIndex(i + 1);
      const prefix = valid.length > 1 ? `${i + 1}/${valid.length}번째 영수증 · ` : '';
      setUploadStep(0);
      setUploadMsg(`${prefix}확인하고 있어요…`);
      // 실제 진행 단계를 알 수 없어(요청 하나로 끝남) 흐름만 보여주는 연출용 타이머다.
      const t1 = setTimeout(() => {
        setUploadMsg(`${prefix}금액·상호·증빙 종류를 정리하고 있어요…`);
        setUploadStep(1);
      }, 3500);
      const t2 = setTimeout(() => {
        setUploadMsg(`${prefix}경비 인정 가능성을 판단하고 있어요…`);
        setUploadStep(2);
      }, 8000);
      try {
        await api.uploadReceipt(valid[i]);
      } catch (e2) {
        if (e2 && e2.status === 401) {
          onRequireLogin && onRequireLogin();
          stoppedByAuth = true;
          clearTimeout(t1);
          clearTimeout(t2);
          break;
        }
        failed.push(valid[i].name);
      } finally {
        clearTimeout(t1);
        clearTimeout(t2);
      }
    }

    load();
    setUploading(false);
    setUploadMsg('');
    setUploadStep(0);
    setUploadIndex(0);
    setUploadTotal(0);
    if (!stoppedByAuth && failed.length) {
      setErr(`${failed.length}개를 올리지 못했어요 — ${failed.join(', ')}`);
    }
  };

  const onDeleted = (id) => setItems((cur) => cur.filter((x) => x.expenseId !== id));
  const onCategoryChanged = (id, category, detail) =>
    setItems((cur) =>
      cur.map((x) =>
        x.expenseId === id
          ? {
              ...x,
              category,
              deductible: detail.deductible,
              tier: detail.tier,
              tierLabel: detail.tierLabel,
              proofValid: detail.proofValid,
              missingFields: detail.missingFields,
            }
          : x
      )
    );

  const highCount = items.filter((x) => x.tier === 'high').length;
  const ambiguousCount = items.filter((x) => x.tier === 'ambiguous').length;
  const lowCount = items.filter((x) => x.tier === 'low').length;
  const approvalRate = items.length ? Math.round((highCount / items.length) * 100) : 0;

  const searchNorm = search.trim().toLowerCase();
  const filteredItems = items
    .filter((x) => tierFilter === 'all' || x.tier === tierFilter)
    .filter((x) => !searchNorm || (x.vendor || '').toLowerCase().includes(searchNorm) || (x.category || '').toLowerCase().includes(searchNorm));
  const filteredTotal = filteredItems.reduce((s, x) => s + x.amount, 0);
  const resetFilters = () => {
    setTierFilter('all');
    setSearch('');
  };

  return (
    <div className="tool">
      <div className="tool__panel exp2">
        {!userId ? (
          <React.Fragment>
            <h2 className="exp-eyebrow"><span className="exp-eyebrow__dot" aria-hidden="true" />지출관리 · 영수증 경비 판정</h2>
            <p className="cvx__empty">
              로그인하면 영수증을 올리고 경비 판정을 받을 수 있어요.{' '}
              {onRequireLogin && (
                <button type="button" style={linkBtn} onClick={onRequireLogin}>로그인</button>
              )}
            </p>
          </React.Fragment>
        ) : (
          <React.Fragment>
            <input
              ref={fileRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              capture="environment"
              multiple
              style={{ display: 'none' }}
              onChange={onFile}
            />
            <div className="exp2__layout">
              <aside className="exp2__side">
                <h2 className="exp-eyebrow"><span className="exp-eyebrow__dot" aria-hidden="true" />지출관리 · 영수증 경비 판정</h2>

                {uploading ? (
                  <div className="exp-ai" role="status" aria-live="polite">
                    <span className="exp-ai__glow exp-ai__glow--a" aria-hidden="true" />
                    <span className="exp-ai__glow exp-ai__glow--b" aria-hidden="true" />
                    <div className="exp-ai__orb" aria-hidden="true">
                      <span className="exp-ai__orb-ring" />
                      <span className="exp-ai__orb-core" />
                    </div>
                    <div className="exp-ai__text">
                      <p className="exp-ai__title">
                        AI가 영수증을 분석하고 있어요
                        {uploadTotal > 1 && ` (${uploadIndex}/${uploadTotal})`}
                      </p>
                      <p className="exp-ai__sub">{uploadMsg || '영수증을 확인하고 있어요…'}</p>
                    </div>
                    <ol className="exp-ai__steps">
                      {ANALYZE_STEPS.map((label, i) => (
                        <li
                          key={label}
                          className={i < uploadStep ? 'is-done' : i === uploadStep ? 'is-active' : ''}
                        >
                          <span className="exp-ai__dot" aria-hidden="true" />
                          {label}
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : (
                  <button type="button" className="exp-upload" onClick={pickFile}>
                    📷 영수증 올리기 (여러 장 선택 가능)
                  </button>
                )}
                {err && <p className="cal__err">{err}</p>}

                {!loading && items.length > 0 && (
                  <React.Fragment>
                    <div className="exp-stats exp-stats--vert">
                      <div className="exp-stat">
                        <span className="exp-stat__lbl">전체 영수증</span>
                        <span className="exp-stat__num">{items.length}건</span>
                      </div>
                      <div className="exp-stat exp-stat--ok">
                        <span className="exp-stat__lbl">경비 인정</span>
                        <span className="exp-stat__num">{highCount}건</span>
                      </div>
                      <div className="exp-stat exp-stat--check">
                        <span className="exp-stat__lbl">확인 필요</span>
                        <span className="exp-stat__num">{ambiguousCount}건</span>
                      </div>
                      <div className="exp-stat exp-stat--bad">
                        <span className="exp-stat__lbl">경비 불인정</span>
                        <span className="exp-stat__num">{lowCount}건</span>
                      </div>
                      <div className="exp-stat exp-stat--accent">
                        <span className="exp-stat__lbl">인정률</span>
                        <span className="exp-stat__num">{approvalRate}%</span>
                      </div>
                    </div>

                    <div className="exp-tabs exp-tabs--vert" role="tablist" aria-label="경비 인정 상태 필터">
                      {TIER_TABS.map((t) => {
                        const count = t.key === 'all' ? items.length : t.key === 'high' ? highCount : t.key === 'ambiguous' ? ambiguousCount : lowCount;
                        return (
                          <button
                            key={t.key}
                            type="button"
                            role="tab"
                            aria-selected={tierFilter === t.key}
                            className={'exp-tab' + (tierFilter === t.key ? ' is-on' : '')}
                            onClick={() => setTierFilter(t.key)}
                          >
                            {t.label} <span className="exp-tab__count">{count}</span>
                          </button>
                        );
                      })}
                    </div>

                    <input
                      type="text"
                      className="exp-search exp-search--full"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="상호·지출항목 검색"
                      aria-label="영수증 검색"
                    />
                    <button
                      type="button"
                      className="exp-excel exp-excel--full"
                      onClick={() => downloadExpensesExcel(filteredItems)}
                    >
                      📊 엑셀로 다운로드
                    </button>
                  </React.Fragment>
                )}
              </aside>

              <div className="exp2__main">
                {loading ? (
                  <p className="ai__hint">불러오는 중…</p>
                ) : items.length === 0 ? (
                  <p className="cvx__empty">아직 올린 영수증이 없어요.</p>
                ) : filteredItems.length === 0 ? (
                  <div className="exp-empty">
                    <p>조건에 맞는 영수증이 없어요.</p>
                    <button type="button" className="exp-empty__reset" onClick={resetFilters}>
                      필터 초기화
                    </button>
                  </div>
                ) : (
                  <React.Fragment>
                    <div className="exp2__mainhead">
                      <span className="exp-toolbar__count">영수증 {filteredItems.length}건</span>
                    </div>
                    <ul className="exp-list exp-list--cards">
                      {filteredItems.map((it) => (
                        <ReceiptCard
                          key={it.expenseId}
                          item={it}
                          onDeleted={onDeleted}
                          onCategoryChanged={onCategoryChanged}
                        />
                      ))}
                    </ul>
                    <div className="exp-total">
                      <span>합계 · 인정 가능성 높음 {filteredItems.filter((x) => x.tier === 'high').length}/{filteredItems.length}건</span>
                      <span className="u-num">{filteredTotal.toLocaleString()}원</span>
                    </div>
                  </React.Fragment>
                )}
              </div>
            </div>
          </React.Fragment>
        )}
      </div>
    </div>
  );
}
