// 반응형 웹앱 홈 맨 위 "오늘 챙길 일". 로그인한 사용자에게만 보인다.
// 다음 로드맵 할 일 · 저장한 공고 마감 · 확인 필요한 영수증 · 다가오는 세금 일정을 카드 4장으로 모은다.
// 기존 API(로드맵 진행 · 저장 공고 · 추천 공고 · 지출 · 일정)만 쓴다.
import React, { useEffect, useMemo, useState } from 'react';
import { api } from '../api.js';
import { ROADMAP, ROADMAP_TASKS } from '../constants.js';
import { eventsByDate, policyDday } from '../utils.js';
import { setHandoff } from './env.js';

const ddayText = (d) => (d === 0 ? 'D-DAY' : `D-${d}`);

export function WebToday({ user, roadmapDone, savedPolicies, onNavigate, onLogin }) {
  const [recs, setRecs] = useState([]);
  const [expenses, setExpenses] = useState(null);
  const [events, setEvents] = useState({});
  const uid = user && user.id;

  useEffect(() => {
    if (!uid) return undefined;
    let alive = true;
    api.recommendations({ limit: 20 }).then((r) => alive && setRecs(r.policies || [])).catch(() => {});
    api.expenses().then((r) => alive && setExpenses(r.expenses || [])).catch(() => alive && setExpenses([]));
    api.calendar().then((r) => alive && setEvents(eventsByDate(r))).catch(() => {});
    return () => { alive = false; };
  }, [uid]);

  const cards = useMemo(() => {
    // ① 다음 로드맵 할 일: 첫 번째로 끝내지 않은 작업
    let next = null;
    for (const s of ROADMAP) {
      const i = (ROADMAP_TASKS[s.k] || []).findIndex((_, j) => !roadmapDone[`${s.k}:${j}`]);
      if (i >= 0) { next = { s, t: ROADMAP_TASKS[s.k][i] }; break; }
    }
    const total = ROADMAP.reduce((n, s) => n + (ROADMAP_TASKS[s.k] || []).length, 0);
    const done = Object.values(roadmapDone).filter(Boolean).length;

    // ② 공고 마감: 저장한 공고 중 가장 가까운 마감, 없으면 추천 공고 중에서
    const nearest = (list) => list
      .map((p) => ({ p, d: policyDday(p.applyEndDate) }))
      .filter((x) => x.d !== null && x.d >= 0)
      .sort((a, b) => a.d - b.d)[0];
    const saved = nearest(savedPolicies || []);
    const rec = saved ? null : nearest(recs);

    // ③ 확인 필요한 영수증
    const pending = (expenses || []).filter((e) => e.tier === 'ambiguous').length;

    // ④ 오늘 이후 가장 가까운 세금 일정
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const tax = Object.entries(events)
      .flatMap(([date, items]) => items.filter((e) => e.type === 'tax').map((e) => ({ ...e, date })))
      .map((e) => ({ ...e, d: Math.round((new Date(e.date) - today) / 86400000) }))
      .filter((e) => e.d >= 0)
      .sort((a, b) => a.d - b.d)[0];

    return [
      {
        key: 'roadmap', tone: 'blue', kicker: `로드맵 ${done}/${total}`,
        title: next ? next.t.t : '모든 할 일을 마쳤어요',
        meta: next ? `${next.s.k}. ${next.s.t} 단계` : '스케일업 단계까지 완료',
        cta: next ? '할 일 보기' : '로드맵 보기',
      },
      saved || rec ? {
        key: 'gov', handoff: { openPolicyId: (saved || rec).p.policyId, item: (saved || rec).p }, tone: (saved || rec).d <= 7 ? 'red' : 'violet',
        kicker: `${saved ? '저장한 공고' : '추천 공고'} · ${ddayText((saved || rec).d)}`,
        title: (saved || rec).p.title,
        meta: (saved || rec).p.source || '',
        cta: '공고 보기',
      } : {
        key: 'gov', tone: 'violet', kicker: '공고 마감', title: '가까운 마감 공고가 없어요',
        meta: '☆를 눌러 관심 공고를 저장해 두세요', cta: '공고 둘러보기',
      },
      {
        key: 'expenses', tone: pending ? 'amber' : 'green', kicker: '영수증',
        handoff: pending ? { filter: 'ambiguous' } : null,
        title: expenses == null ? '불러오는 중…' : pending ? `확인 필요한 영수증 ${pending}건` : '확인할 영수증이 없어요',
        meta: pending ? '경비로 인정되는지 직접 확인해 주세요' : '영수증을 올리면 경비 인정 여부를 판정해요',
        cta: pending ? '확인하러 가기' : '영수증 올리기',
      },
      tax ? {
        key: 'tax', tone: tax.d <= 7 ? 'red' : 'green', kicker: `세금 일정 · ${ddayText(tax.d)}`,
        title: tax.title, meta: `${tax.date.replaceAll('-', '.')}까지`, cta: 'AI 세무에 묻기',
      } : {
        key: 'tax', tone: 'green', kicker: '세금 일정', title: '다가오는 세금 일정이 없어요',
        meta: '궁금한 세무는 AI 세무에서', cta: 'AI 세무 열기',
      },
    ];
  }, [recs, savedPolicies, roadmapDone, expenses, events]);

  if (!user) {
    return (
      <section className="wtoday" aria-label="로그인 안내">
        <div className="wrap">
          <div className="wtoday__login">
            <span>
              <b>로그인하면 오늘 챙길 일을 모아 드려요</b>
              <small>다음 로드맵 할 일 · 공고 마감 · 확인할 영수증 · 세금 일정</small>
            </span>
            {onLogin && <button type="button" onClick={onLogin}>로그인</button>}
          </div>
        </div>
      </section>
    );
  }
  return (
    <section className="wtoday" aria-labelledby="wtoday-title">
      <div className="wrap">
        <h2 id="wtoday-title" className="wtoday__title">
          {user.name}님, <span>오늘 챙길 일</span>
        </h2>
        <div className="wtoday__grid">
          {cards.map((c) => (
            <button key={c.key} type="button" className={'wtoday__card is-' + c.tone} onClick={() => { if (c.handoff) setHandoff(c.key, c.handoff); onNavigate(c.key); }}>
              <span className="wtoday__kicker">{c.kicker}</span>
              <b className="wtoday__card-title">{c.title}</b>
              {c.meta && <span className="wtoday__meta">{c.meta}</span>}
              <span className="wtoday__cta">{c.cta} ›</span>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
