// 05 공고지원 AI: 세그먼트(전체·모집 중·저장) → 적합도 순 공고 페이지 목록 → 보라 "공고 상담" 박스.
// 공고를 누르면 바텀시트(기간·대상·지원 내용·서류 + 저장·원문·AI 상담). 상담은 채팅 화면(category=policy).
import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api.js';
import { GOV_CHIPS } from '../constants.js';
import { policyDday, policyDdayLabel } from '../utils.js';
import { ChatBubbles, ChatInput, FeatureHeader, Pager, Seg, Sheet, featureOf, paginate, usePageSize, useChat, useToast } from './ui.jsx';

function originalUrl(item) {
  for (const c of [item && item.sourceUrl, item && item.source]) {
    try {
      const u = new URL(c);
      if (u.protocol === 'http:' || u.protocol === 'https:') return u.href;
    } catch { /* 출처명 */ }
  }
  return '';
}

function PolicySheet({ item, saved, onToggleSave, onConsult, onClose }) {
  const [detail, setDetail] = useState(null);
  const [summary, setSummary] = useState(null);
  const [state, setState] = useState('loading');
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let alive = true;
    setState('loading');
    api.policy(item.policyId)
      .then(async (d) => {
        if (!alive) return;
        setDetail(d);
        if (!d.announcementId) { setState('none'); return; }
        try {
          const s = await api.announcementSummary(d.announcementId);
          if (alive) { setSummary(s); setState('ready'); }
        } catch { if (alive) setState('none'); }
      })
      .catch(() => alive && setState('none'));
    return () => { alive = false; };
  }, [item.policyId]);

  const pol = detail && detail.policy;
  const rows = [
    ['기간', summary?.period || detail?.applyPeriod || policyDdayLabel(policyDday(item.applyEndDate))],
    ['대상', summary?.target || pol?.target || item.target || '공고문 확인 필요'],
    ['지원 내용', summary?.benefit || pol?.benefit || item.benefit || '공고문 확인 필요'],
    ['서류', summary?.documents || '공고문 확인 필요'],
  ];
  const url = originalUrl(item);
  return (
    <Sheet open onClose={onClose} title={item.title}>
      <p className="m-sheet__sub">{item.source}{state === 'loading' ? ' · AI가 공고를 요약하는 중…' : ''}</p>
      <dl className="m-dl">
        {rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
      </dl>
      <div className="m-row2">
        <button type="button" className={'m-btn m-btn--glass' + (saved ? ' is-saved' : '')} disabled={saving}
          onClick={async () => { setSaving(true); try { await onToggleSave(item); } finally { setSaving(false); } }}>
          {saved ? '★ 저장됨' : '☆ 저장'}
        </button>
        {url
          ? <a className="m-btn m-btn--glass" href={url} target="_blank" rel="noreferrer">원문 확인하기</a>
          : <button type="button" className="m-btn m-btn--glass" disabled>원문 없음</button>}
      </div>
      <button type="button" className="m-btn m-btn--violet" onClick={() => onConsult(item)}>이 공고, AI와 상담하기</button>
    </Sheet>
  );
}

export function MGov({ user, params, savedPolicies, onToggleSavedPolicy, onHome, onMenu }) {
  const toast = useToast();
  const [view, setView] = useState(params.chat ? 'chat' : 'list');
  const [seg, setSeg] = useState('all');
  const [recs, setRecs] = useState(null);
  const [profile, setProfile] = useState(null);
  const [page, setPage] = useState(0);
  const [openItem, setOpenItem] = useState(null);
  const chat = useChat('policy', user && user.id);
  const sentRef = useRef(null);
  const [listRef, size] = usePageSize(72, 8);

  useEffect(() => {
    if (!user) return undefined;
    let alive = true;
    api.recommendations({ limit: 20 }).then((r) => alive && setRecs(r.policies || [])).catch(() => alive && setRecs([]));
    api.businessProfile().then((p) => alive && setProfile(p)).catch(() => {});
    return () => { alive = false; };
  }, [user]);
  useEffect(() => setPage(0), [seg]);

  // 홈 브리핑에서 특정 공고를 열거나, 홈 입력창에서 질문을 들고 왔을 때
  useEffect(() => {
    if (params.openPolicyId && recs) {
      const it = recs.find((r) => r.policyId === params.openPolicyId);
      if (it) setOpenItem(it);
    }
  }, [params.openPolicyId, recs]);
  useEffect(() => {
    if (chat.ready && params.question && sentRef.current !== params.nonce) {
      sentRef.current = params.nonce;
      setView('chat');
      chat.send(params.question);
    }
  }, [chat.ready, params, chat]);

  const savedIds = new Set((savedPolicies || []).map((p) => p.policyId));
  const all = recs || [];
  const list = seg === 'saved' ? savedPolicies || []
    : seg === 'open' ? all.filter((p) => { const d = policyDday(p.applyEndDate); return d === null || d >= 0; })
      : all;
  const { pages, page: p, items } = paginate(list, page, size);

  const toggleSave = async (item) => {
    try {
      await onToggleSavedPolicy(item);
      toast(savedIds.has(item.policyId) ? '저장을 해제했어요' : '관심 공고로 저장했어요');
    } catch {
      toast('저장 상태를 바꾸지 못했어요');
    }
  };
  const consult = (q) => {
    setOpenItem(null);
    setView('chat');
    chat.send(q);
  };

  if (view === 'chat') {
    return (
      <div className="m-screen">
        <FeatureHeader feature={{ no: '05', name: '공고 상담' }} onHome={onHome} onMenu={onMenu}
          backLabel="공고" onBack={() => setView('list')} />
        <div className="m-body">
          <ChatBubbles rows={chat.rows} max={4} empty="지원 자격 · 서류 · 사업계획서 방향을 물어보세요" />
          <div className="m-sugg">
            {GOV_CHIPS.slice(0, 2).map((c) => (
              <button key={c} type="button" className="m-glass m-sugg__btn" onClick={() => chat.send(c)} disabled={chat.busy}>{c}</button>
            ))}
          </div>
          <ChatInput onSend={chat.send} busy={chat.busy} placeholder="공고에 대해 물어보세요" />
        </div>
      </div>
    );
  }

  const cond = [profile && profile.industry, user && user.region].filter(Boolean).join(' · ');
  return (
    <div className="m-screen">
      <FeatureHeader feature={featureOf('gov')} onHome={onHome} onMenu={onMenu} />
      <div className="m-body">
        <Seg value={seg} onChange={setSeg} items={[
          { key: 'all', label: '전체' },
          { key: 'open', label: '모집 중' },
          { key: 'saved', label: '저장', count: savedIds.size },
        ]} />
        <p className="m-note">{cond ? `${cond} 조건 · ` : ''}적합도 순</p>
        <div className="m-list" ref={listRef}>
          {recs === null && <p className="m-empty">불러오는 중…</p>}
          {recs !== null && list.length === 0 && <p className="m-empty">{seg === 'saved' ? '저장한 공고가 없어요' : '조건에 맞는 공고가 없어요'}</p>}
          {items.map((it) => {
            const d = policyDday(it.applyEndDate);
            const closed = d !== null && d < 0;
            return (
              <button key={it.policyId} type="button" className={'m-glass m-grow' + (closed ? ' is-closed' : '')} onClick={() => setOpenItem(it)}>
                <span className="m-fit">{it.matchScore != null ? `${it.matchScore}` : '–'}<small>적합</small></span>
                <span className="m-grow__info">
                  <b>{savedIds.has(it.policyId) ? '★ ' : ''}{it.title}</b>
                  <span>{it.source}</span>
                </span>
                <span className={'m-dday' + (d !== null && d >= 0 && d <= 7 ? ' is-urgent' : '')}>{policyDdayLabel(d)}</span>
              </button>
            );
          })}
        </div>
        <Pager page={p} pages={pages} onChange={setPage} />
        <section className="m-consult">
          <div className="m-consult__head"><b>공고 상담</b><button type="button" onClick={() => setView('chat')}>대화 열기 ›</button></div>
          <div className="m-consult__qs">
            {GOV_CHIPS.slice(0, 2).map((c) => (
              <button key={c} type="button" onClick={() => consult(c)}>{c}</button>
            ))}
          </div>
        </section>
      </div>
      {openItem && (
        <PolicySheet item={openItem} saved={savedIds.has(openItem.policyId)} onToggleSave={toggleSave}
          onConsult={(it) => consult(`'${it.title}' 공고의 지원 자격과 준비 서류를 알려주세요`)} onClose={() => setOpenItem(null)} />
      )}
    </div>
  );
}
