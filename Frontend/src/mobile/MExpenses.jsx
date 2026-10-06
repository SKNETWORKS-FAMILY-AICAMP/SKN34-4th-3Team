// 03 지출관리: 요약 카드(금액 기준 인정률 · 합계 · 3색 막대 · 상태별 금액) → 밑줄 탭 → 한 카드 목록(스크롤)
// + 떠 있는 "+ 영수증" 버튼. 행을 누르면 바텀시트에서 영수증 이미지를 보고 지출항목을 바꿔 다시 판정한다.
// 지출관리 화면만 앱 공통 3b 규칙(스크롤 금지 · 페이지 넘김 · 엑셀 버튼) 대신 이 화면 전용 시안을 따른다.
import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api.js';
import { prepareReceiptImage } from '../receiptImage.js';
import { Burger, Sheet, useToast } from './ui.jsx';

const CATS = ['사무용품', '통신비', '차량유지비', '광고선전비', '임차료', '복리후생비', '접대비', '교육·도서', '기타'];
const TIER = {
  high: { label: '인정', cls: 'ok' },
  ambiguous: { label: '확인 필요', cls: 'chk' },
  low: { label: '불인정', cls: 'bad' },
};
const tierOf = (x) => TIER[x.tier] || TIER.ambiguous;

const won = (n) => `${Number(n || 0).toLocaleString('ko-KR')}원`;
const shortDate = (d) => (d ? String(d).slice(2, 10).replaceAll('-', '.') : '날짜 미상');
const isUnknown = (v) => !v || v === '상호 미상';

export function MExpenses({ user, params, onHome, onMenu, onLogin }) {
  const toast = useToast();
  const [items, setItems] = useState(null);
  const [filter, setFilter] = useState(params.filter || 'all');
  const [uploading, setUploading] = useState(0);
  const [selId, setSelId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [img, setImg] = useState({ id: null, url: '', state: 'idle' });
  const fileRef = useRef(null);

  const load = () => api.expenses()
    .then((r) => setItems([...((r && r.expenses) || [])].sort((a, b) => b.expenseId - a.expenseId)))
    .catch(() => setItems([]));
  useEffect(() => { if (user) load(); }, [user]);

  const list = items || [];
  const sel = list.find((x) => x.expenseId === selId) || null;

  // 시트를 열면 영수증 원본 이미지를 받아 온다(인증이 필요해 blob URL로 띄운다).
  useEffect(() => {
    if (!sel || !sel.receiptId) { setImg({ id: null, url: '', state: 'none' }); return undefined; }
    let alive = true;
    let url = '';
    setImg({ id: sel.receiptId, url: '', state: 'loading' });
    api.receiptImage(sel.receiptId)
      .then((blob) => {
        if (!alive) return;
        url = URL.createObjectURL(blob);
        setImg({ id: sel.receiptId, url, state: 'ready' });
      })
      .catch(() => alive && setImg({ id: sel.receiptId, url: '', state: 'none' }));
    return () => { alive = false; if (url) URL.revokeObjectURL(url); };
  }, [sel && sel.receiptId]);

  // 인정률 · 막대는 금액 기준, 탭 숫자는 건수 기준
  const total = list.reduce((s, x) => s + (x.amount || 0), 0);
  const amt = { ok: 0, chk: 0, bad: 0 };
  const cnt = { ok: 0, chk: 0, bad: 0 };
  list.forEach((x) => { const c = tierOf(x).cls; amt[c] += x.amount || 0; cnt[c] += 1; });
  const rate = total ? Math.round((amt.ok / total) * 100) : 0;
  const pct = (c) => (total ? (amt[c] / total) * 100 : 0);
  let seen = false;
  const segs = ['ok', 'chk', 'bad'].map((c) => {
    const p = pct(c);
    const sep = seen && p > 0;
    if (p > 0) seen = true;
    return { c, p, sep };
  });

  const tabs = [
    { key: 'all', label: '전체', n: list.length },
    { key: 'high', label: '인정', n: cnt.ok },
    { key: 'ambiguous', label: '확인', n: cnt.chk },
    { key: 'low', label: '불인정', n: cnt.bad },
  ];
  const shown = filter === 'all' ? list : list.filter((x) => (x.tier || 'ambiguous') === filter);
  const placeholders = Array.from({ length: uploading }, (_, i) => ({ placeholder: true, expenseId: 'up' + i }));
  const rows = [...placeholders, ...shown];

  const upload = async (files) => {
    const valid = files.filter((f) => ['image/jpeg', 'image/png', 'image/webp'].includes(f.type));
    if (valid.length < files.length) toast('JPEG·PNG·WebP 이미지만 올릴 수 있어요');
    if (!valid.length) return;
    setFilter('all');
    setUploading(valid.length);
    let failed = 0;
    for (const f of valid) {
      try {
        // 카메라 원본처럼 큰 사진은 줄여서 올린다. 줄여도 4MB를 넘으면 실패로 센다.
        const ready = await prepareReceiptImage(f);
        if (ready) await api.uploadReceipt(ready);
        else failed += 1;
      } catch (e) {
        if (e && e.status === 401) { onLogin(); break; }
        failed += 1;
      }
      setUploading((n) => Math.max(0, n - 1));
    }
    setUploading(0);
    await load();
    toast(failed ? `${failed}건을 올리지 못했어요` : '영수증을 판독했어요');
  };

  const changeCategory = async (category) => {
    if (!sel || busy || category === sel.category) return;
    setBusy(true);
    try {
      await api.updateExpenseCategory(sel.expenseId, category);
      await load();
      toast('지출항목을 바꾸고 다시 판정했어요');
    } catch {
      toast('바꾸지 못했어요. 잠시 후 다시 시도해 주세요');
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!sel || busy || !window.confirm('이 영수증과 지출 기록을 삭제할까요?')) return;
    setBusy(true);
    try {
      await api.deleteExpense(sel.expenseId);
      setItems((cur) => cur.filter((x) => x.expenseId !== sel.expenseId));
      setSelId(null);
      toast('삭제했어요');
    } catch {
      toast('삭제하지 못했어요');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="m-screen m-xp">
      <header className="m-xp__head">
        <button type="button" className="m-xp__back" onClick={onHome}>‹ 홈</button>
        <h1 className="m-xp__title"><span>03</span>지출관리</h1>
        <Burger onClick={onMenu} />
      </header>

      <section className="m-xp__sum" aria-label="지출 요약">
        <div className="m-xp__sumtop">
          <div>
            <span className="m-xp__k">경비 인정률</span>
            <b className="m-xp__rate">{rate}<small>%</small></b>
          </div>
          <div className="m-xp__total"><span>합계</span><b>{won(total)}</b></div>
        </div>
        <div className="m-xp__bar" role="img" aria-label={`인정 ${won(amt.ok)}, 확인 필요 ${won(amt.chk)}, 불인정 ${won(amt.bad)}`}>
          {segs.map((s) => <i key={s.c} className={s.c + (s.sep ? ' sep' : '')} style={{ width: s.p + '%' }} />)}
        </div>
        <div className="m-xp__legend">
          {[['ok', '인정'], ['chk', '확인 필요'], ['bad', '불인정']].map(([c, label]) => (
            <div key={c}><span><i className={'m-xp__dot ' + c} />{label}</span><b>{won(amt[c])}</b></div>
          ))}
        </div>
      </section>

      <nav className="m-xp__tabs" role="tablist">
        {tabs.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={filter === t.key}
            className={'m-xp__tab' + (filter === t.key ? ' is-on' : '')} onClick={() => setFilter(t.key)}>
            {t.label}<em>{t.n}</em>
          </button>
        ))}
      </nav>

      <div className="m-xp__scroll">
        {items === null && <p className="m-xp__empty">불러오는 중…</p>}
        {items !== null && rows.length === 0 && <p className="m-xp__empty">해당하는 지출이 없어요</p>}
        {rows.length > 0 && (
          <div className="m-xp__list">
            {rows.map((x) => (x.placeholder ? (
              <div key={x.expenseId} className="m-xp__row is-loading">
                <span className="m-spin" aria-hidden="true" />
                <span className="m-xp__info"><b>OCR 분석 중…</b><span>영수증 글자를 읽고 있어요</span></span>
              </div>
            ) : (
              <button key={x.expenseId} type="button" className="m-xp__row" onClick={() => setSelId(x.expenseId)}>
                <i className={'m-xp__dot ' + tierOf(x).cls} />
                <span className="m-xp__info">
                  <b className={isUnknown(x.vendor) ? 'is-unknown' : ''}>{x.vendor || '상호 미상'}</b>
                  <span>{shortDate(x.date)} · {x.category}</span>
                </span>
                <span className="m-xp__right">
                  <b>{won(x.amount)}</b>
                  <span className={'m-xp__chip ' + tierOf(x).cls}>{tierOf(x).label}</span>
                </span>
              </button>
            )))}
          </div>
        )}
      </div>

      <button type="button" className="m-xp__fab" onClick={() => fileRef.current && fileRef.current.click()} disabled={!!uploading}>
        + 영수증
      </button>
      <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden
        onChange={(e) => { upload(Array.from(e.target.files || [])); e.target.value = ''; }} />

      <Sheet open={!!sel} onClose={() => setSelId(null)} className="m-xp-sheet" title="">
        {sel && (
          <>
            <div className="m-xp-sheet__top">
              <div>
                <span className="m-xp-sheet__meta">{shortDate(sel.date)} · {sel.category}</span>
                <h2 className={'m-xp-sheet__name' + (isUnknown(sel.vendor) ? ' is-unknown' : '')}>{sel.vendor || '상호 미상'}</h2>
              </div>
              <span className={'m-xp__chip ' + tierOf(sel).cls}>{tierOf(sel).label}</span>
            </div>
            <b className="m-xp-sheet__amt">{won(sel.amount)}</b>
            <div className="m-xp-sheet__img">
              {img.state === 'ready' && img.id === sel.receiptId
                ? <img src={img.url} alt={`${sel.vendor || '상호 미상'} 영수증`} />
                : <span>{img.state === 'loading' ? '영수증 불러오는 중…' : '영수증 이미지 없음'}</span>}
            </div>
            <div className="m-xp-sheet__sub">
              <label>
                <span>지출항목</span>
                <select value={CATS.includes(sel.category) ? sel.category : ''} disabled={busy}
                  onChange={(e) => changeCategory(e.target.value)}>
                  {!CATS.includes(sel.category) && <option value="" disabled>{sel.category || '선택'}</option>}
                  {CATS.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
              <button type="button" onClick={remove} disabled={busy}>삭제</button>
            </div>
          </>
        )}
      </Sheet>
    </div>
  );
}
