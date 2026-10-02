// 06 마이페이지: 프로필 → 요약 3칸(로드맵 · 저장 공고 · 확인 필요) → 일정 달력(남은 높이 전부) → 메뉴 2×2.
// 사업자 정보 · 알림 설정 · 구독·결제는 PC 마이페이지와 같은 부품을 바텀시트 안에서 그대로 쓴다.
import React, { useEffect, useMemo, useState } from 'react';
import { api } from '../api.js';
import { ROADMAP, ROADMAP_TASKS, WEEKDAYS } from '../constants.js';
import { eventsByDate, dayKey } from '../utils.js';
import { BillingPanel, ProfileSettings } from '../pages/MyPage.jsx';
import { FeatureHeader, Sheet, featureOf } from './ui.jsx';

export function MMyPage({ user, go, roadmapDone, savedPolicies, onHome, onMenu, onLogout, onLogin, onProfileSaved }) {
  const [profile, setProfile] = useState(null);
  const [pendingN, setPendingN] = useState(null);
  const [events, setEvents] = useState({});
  const now = new Date();
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() });
  const [picked, setPicked] = useState(dayKey(now.getFullYear(), now.getMonth(), now.getDate()));
  const [sheet, setSheet] = useState('');

  useEffect(() => {
    if (!user) return undefined;
    let alive = true;
    api.businessProfile().then((p) => alive && setProfile(p)).catch(() => {});
    api.expenses().then((r) => alive && setPendingN((r.expenses || []).filter((e) => e.tier === 'ambiguous').length)).catch(() => {});
    api.calendar().then((r) => alive && setEvents(eventsByDate(r))).catch(() => {});
    return () => { alive = false; };
  }, [user]);

  const total = ROADMAP.reduce((n, s) => n + (ROADMAP_TASKS[s.k] || []).length, 0);
  const pct = total ? Math.round((Object.values(roadmapDone).filter(Boolean).length / total) * 100) : 0;

  // 달력에는 내 일정 · 세금 일정 · 저장한 공고 마감만 표시한다(PC 공고지원 화면과 같은 규칙).
  const savedIds = useMemo(() => new Set((savedPolicies || []).map((p) => p.policyId)), [savedPolicies]);
  const visible = useMemo(() => {
    const out = {};
    Object.entries(events).forEach(([d, items]) => {
      const shown = items.filter((e) => e.mine || e.type === 'tax' || (e.policyId != null && savedIds.has(e.policyId)));
      if (shown.length) out[d] = shown;
    });
    return out;
  }, [events, savedIds]);

  const first = new Date(ym.y, ym.m, 1).getDay();
  const days = new Date(ym.y, ym.m + 1, 0).getDate();
  const cells = [...Array(first).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
  const todayKey = dayKey(now.getFullYear(), now.getMonth(), now.getDate());
  const moveMonth = (d) => setYm(({ y, m }) => {
    const t = new Date(y, m + d, 1);
    return { y: t.getFullYear(), m: t.getMonth() };
  });
  const pickedEvents = visible[picked] || [];

  if (!user) {
    return (
      <div className="m-screen">
        <FeatureHeader feature={featureOf('mypage')} onHome={onHome} onMenu={onMenu} />
        <div className="m-body"><button type="button" className="m-btn m-btn--primary" onClick={onLogin}>로그인</button></div>
      </div>
    );
  }

  return (
    <div className="m-screen">
      <FeatureHeader feature={featureOf('mypage')} onHome={onHome} onMenu={onMenu} />
      <div className="m-body">
        <section className="m-glass m-prof">
          <span className="m-prof__ava" aria-hidden="true">{(user.name || '?').slice(0, 1)}</span>
          <div className="m-prof__info">
            <b>{user.name}님</b>
            <span>{[profile && profile.businessType, profile && profile.industry, user.region].filter(Boolean).join(' · ') || '사업자 정보를 입력해 주세요'}</span>
          </div>
          <button type="button" className="m-prof__out" onClick={onLogout}>로그아웃</button>
        </section>

        <div className="m-sum3">
          <button type="button" className="m-glass" onClick={() => go('roadmap')}><b>{pct}%</b><span>로드맵</span></button>
          <button type="button" className="m-glass" onClick={() => go('gov', {})}><b>{(savedPolicies || []).length}</b><span>저장 공고</span></button>
          <button type="button" className="m-glass" onClick={() => go('expenses', { filter: 'ambiguous' })}><b>{pendingN == null ? '–' : pendingN}</b><span>확인 필요</span></button>
        </div>

        <section className="m-glass m-cal">
          <div className="m-cal__head">
            <b>일정</b>
            <div className="m-pager m-pager--inline">
              <button type="button" onClick={() => moveMonth(-1)} aria-label="이전 달">‹</button>
              <span className="m-pager__n">{ym.y}.{String(ym.m + 1).padStart(2, '0')}</span>
              <button type="button" onClick={() => moveMonth(1)} aria-label="다음 달">›</button>
            </div>
          </div>
          <div className="m-cal__grid">
            {WEEKDAYS.map((w, i) => <span key={w} className={'m-cal__wd' + (i === 0 ? ' is-sun' : '')}>{w}</span>)}
            {cells.map((d, i) => {
              if (!d) return <span key={'e' + i} />;
              const key = dayKey(ym.y, ym.m, d);
              const evs = visible[key] || [];
              return (
                <button key={key} type="button"
                  className={'m-cal__d' + (key === todayKey ? ' is-today' : '') + (key === picked ? ' is-picked' : '')}
                  onClick={() => setPicked(key)}>
                  {d}
                  <span className="m-cal__dots">
                    {evs.some((e) => e.type === 'tax') && <i className="tax" />}
                    {evs.some((e) => e.type !== 'tax') && <i className="pol" />}
                  </span>
                </button>
              );
            })}
          </div>
          <p className="m-cal__line">
            <span>{picked.slice(5).replace('-', '/')}</span>
            {pickedEvents.length ? `${pickedEvents[0].title}${pickedEvents.length > 1 ? ` 외 ${pickedEvents.length - 1}건` : ''}` : '등록된 일정이 없어요'}
          </p>
        </section>

        <div className="m-menu4">
          <button type="button" className="m-glass" onClick={() => setSheet('profile')}>사업자 정보</button>
          <button type="button" className="m-glass" onClick={() => setSheet('notif')}>알림 설정</button>
          <button type="button" className="m-glass" onClick={() => setSheet('billing')}>구독 · 결제</button>
          <button type="button" className="m-glass" onClick={() => go('bizplan')}>사업계획서</button>
        </div>
      </div>

      <Sheet open={!!sheet} onClose={() => setSheet('')} className="m-sheet--tall"
        title={{ profile: '사업자 정보', notif: '알림 설정', billing: '구독 · 결제' }[sheet]}>
        <div className="m-embed">
          {sheet === 'profile' && <ProfileSettings user={user} only="profile" onSaved={(u) => { onProfileSaved && onProfileSaved(u); api.businessProfile().then(setProfile).catch(() => {}); }} />}
          {sheet === 'notif' && <ProfileSettings user={user} only="notif" />}
          {sheet === 'billing' && <BillingPanel onRequireLogin={onLogin} />}
        </div>
      </Sheet>
    </div>
  );
}
