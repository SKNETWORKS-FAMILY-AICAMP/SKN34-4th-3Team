// 홈: 인사 → AI 입력창(세무/공고 모드) → 기능 그리드 3×2 → 오늘의 브리핑(카드 스택, 남은 높이 전부).
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api.js';
import { ROADMAP, ROADMAP_TASKS } from '../constants.js';
import { eventsByDate, policyDday } from '../utils.js';
import { Burger, FEATURES, MLogo, SendIcon } from './ui.jsx';

const MODES = [
  { key: 'tax', no: '02', label: '세무 질문', placeholder: '예: 노트북도 경비처리 되나요?' },
  { key: 'gov', no: '05', label: '공고 상담', placeholder: '예: 예비창업패키지 자격이 궁금해요' },
];

export function MHome({ user, go, onMenu, onLogin, roadmapDone }) {
  const [mode, setMode] = useState('tax');
  const [text, setText] = useState('');
  const [profile, setProfile] = useState(null);
  const [recs, setRecs] = useState([]);
  const [expenses, setExpenses] = useState(null);
  const [events, setEvents] = useState({});
  const [idx, setIdx] = useState(0);
  const touch = useRef(null);
  const uid = user && user.id;

  useEffect(() => {
    if (!uid) return undefined;
    let alive = true;
    api.businessProfile().then((p) => alive && setProfile(p)).catch(() => {});
    api.recommendations({ limit: 20 }).then((r) => alive && setRecs(r.policies || [])).catch(() => {});
    api.expenses().then((r) => alive && setExpenses(r.expenses || [])).catch(() => {});
    api.calendar().then((r) => alive && setEvents(eventsByDate(r))).catch(() => {});
    return () => { alive = false; };
  }, [uid]);

  const cards = useMemo(() => {
    const out = [];
    // ① 마감 임박 공고: 아직 마감 전인 추천 공고 중 가장 가까운 것
    const open = recs
      .map((p) => ({ p, d: policyDday(p.applyEndDate) }))
      .filter((x) => x.d !== null && x.d >= 0)
      .sort((a, b) => a.d - b.d)[0];
    out.push(open ? {
      key: 'deadline', tone: 'violet', kicker: `마감 임박 공고 · D-${open.d}`, title: open.p.title,
      meta: [open.p.source, open.p.benefit].filter(Boolean).join(' · '), cta: '공고 보기',
      onClick: () => go('gov', { openPolicyId: open.p.policyId }),
    } : {
      key: 'deadline', tone: 'violet', kicker: '마감 임박 공고', title: '지금 마감이 가까운 추천 공고가 없어요',
      meta: '조건에 맞는 공고를 둘러보세요', cta: '공고 둘러보기', onClick: () => go('gov'),
    });
    // ② 로드맵 다음 할 일: 첫 번째로 완료하지 않은 작업
    let next = null;
    for (const s of ROADMAP) {
      const i = (ROADMAP_TASKS[s.k] || []).findIndex((_, j) => !roadmapDone[`${s.k}:${j}`]);
      if (i >= 0) { next = { s, t: ROADMAP_TASKS[s.k][i] }; break; }
    }
    out.push(next ? {
      key: 'roadmap', tone: 'blue', kicker: `로드맵 다음 할 일 · ${next.s.k}. ${next.s.t}`, title: next.t.t,
      meta: next.s.d, cta: '로드맵 열기', onClick: () => go('roadmap', { openStep: next.s.k }),
    } : {
      key: 'roadmap', tone: 'blue', kicker: '로드맵', title: '모든 작업을 마쳤어요', meta: '스케일업 단계까지 완료', cta: '로드맵 보기',
      onClick: () => go('roadmap'),
    });
    // ③ 영수증 판정 대기
    const pending = (expenses || []).filter((e) => e.tier === 'ambiguous');
    out.push({
      key: 'receipts', tone: 'amber', kicker: '영수증 판정 대기',
      title: expenses == null ? '영수증을 불러오는 중' : pending.length ? `확인이 필요한 영수증 ${pending.length}건` : '확인할 영수증이 없어요',
      meta: pending.length ? '경비 인정 여부를 확인해 주세요' : '영수증을 올리면 경비 인정 여부를 판정해요',
      cta: pending.length ? '확인하러 가기' : '영수증 올리기',
      onClick: () => go('expenses', { filter: pending.length ? 'ambiguous' : 'all' }),
    });
    // ④ 세금 일정: 오늘 이후 가장 가까운 세금 일정
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const tax = Object.entries(events)
      .flatMap(([date, items]) => items.filter((e) => e.type === 'tax').map((e) => ({ ...e, date })))
      .map((e) => ({ ...e, d: Math.round((new Date(e.date) - today) / 86400000) }))
      .filter((e) => e.d >= 0)
      .sort((a, b) => a.d - b.d)[0];
    out.push(tax ? {
      key: 'tax', tone: 'green', kicker: `세금 일정 · D-${tax.d}`, title: tax.title,
      meta: `${tax.date.replaceAll('-', '.')} 까지${tax.note ? ' · ' + tax.note : ''}`, cta: 'AI 세무에 물어보기',
      onClick: () => go('tax', { question: `${tax.title} 준비할 것을 알려주세요` }),
    } : {
      key: 'tax', tone: 'green', kicker: '세금 일정', title: '다가오는 세금 일정이 없어요', meta: '세무 질문은 AI 세무에서',
      cta: 'AI 세무 열기', onClick: () => go('tax'),
    });
    return out;
  }, [recs, roadmapDone, expenses, events, go]);

  const n = cards.length;
  const card = cards[idx % n];
  const move = (d) => setIdx((i) => (i + d + n) % n);

  const send = (e) => {
    e.preventDefault();
    const q = text.trim();
    if (!q) return;
    if (!user) { onLogin(); return; }
    go(mode, { question: q, chat: true });
    setText('');
  };

  const m = MODES.find((x) => x.key === mode);
  const cond = profile
    ? [profile.businessType, profile.industry, user && user.region].filter(Boolean).join(' · ')
    : user ? [user.region].filter(Boolean).join(' · ') : '로그인하고 맞춤 안내를 받아 보세요';

  return (
    <div className="m-screen m-home">
      <header className="m-hhead">
        <MLogo onClick={() => {}} />
        <Burger onClick={onMenu} />
      </header>

      <section className="m-greet">
        <p className="m-greet__cond"><i className="m-dot" />{cond}</p>
        <h1 className="m-greet__title">{user ? `${user.name}님,` : '안녕하세요,'}<br />무엇을 도와드릴까요?</h1>
      </section>

      <form className="m-glass m-ask" onSubmit={send}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder={m.placeholder} aria-label="AI에게 질문" />
        <div className="m-ask__row">
          {MODES.map((x) => (
            <button key={x.key} type="button" className={'m-chip' + (mode === x.key ? ' is-on' : '')} onClick={() => setMode(x.key)}>
              <span className="m-no">{x.no}</span>{x.label}
            </button>
          ))}
          <button type="submit" className={'m-send' + (text.trim() ? ' is-on' : '')} aria-label="보내기"><SendIcon /></button>
        </div>
      </form>

      <nav className="m-grid" aria-label="기능">
        {FEATURES.map((f) => (
          <button key={f.key} type="button" className="m-glass m-grid__btn" onClick={() => go(f.key)}>
            <span className="m-no">{f.no}</span>
            <b>{f.short}</b>
          </button>
        ))}
      </nav>

      <section className="m-brief" aria-label="오늘의 브리핑">
        <div className="m-brief__head">
          <h2>오늘의 브리핑</h2>
          <div className="m-pager m-pager--inline">
            <button type="button" onClick={() => move(-1)} aria-label="이전 브리핑">‹</button>
            <span className="m-pager__n">{(idx % n) + 1} / {n}</span>
            <button type="button" onClick={() => move(1)} aria-label="다음 브리핑">›</button>
          </div>
        </div>
        <div className="m-brief__stack"
          onTouchStart={(e) => { touch.current = e.touches[0].clientX; }}
          onTouchEnd={(e) => {
            if (touch.current == null) return;
            const dx = e.changedTouches[0].clientX - touch.current;
            if (Math.abs(dx) > 40) move(dx < 0 ? 1 : -1);
            touch.current = null;
          }}>
          <span className="m-brief__ghost m-brief__ghost--2" aria-hidden="true" />
          <span className="m-brief__ghost m-brief__ghost--1" aria-hidden="true" />
          {user ? (
            <article key={card.key} className={'m-brief__card is-' + card.tone}>
              <p className="m-brief__kicker">{card.kicker}</p>
              <h3 className="m-brief__title">{card.title}</h3>
              <p className="m-brief__meta">{card.meta}</p>
              <button type="button" className="m-pill" onClick={card.onClick}>{card.cta} ›</button>
            </article>
          ) : (
            <article className="m-brief__card is-blue">
              <p className="m-brief__kicker">시작하기</p>
              <h3 className="m-brief__title">로그인하면 오늘 챙길 일을 모아 드려요</h3>
              <p className="m-brief__meta">마감 공고 · 로드맵 · 영수증 · 세금 일정</p>
              <button type="button" className="m-pill" onClick={onLogin}>로그인 ›</button>
            </article>
          )}
        </div>
        <div className="m-dots" aria-hidden="true">
          {cards.map((c, i) => <i key={c.key} className={i === idx % n ? 'is-on' : ''} />)}
        </div>
      </section>
    </div>
  );
}
