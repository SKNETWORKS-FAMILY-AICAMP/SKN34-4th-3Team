import React, { useState, useEffect, useRef } from 'react';
import { useApi, api } from '../api.js';
import { DEADLINES, HERO_TITLE, METRICS, CHAT, ROADMAP, WEEKDAYS } from '../constants.js';
import { pad2, dayKey, CAL_EVENTS, eventsByDate } from '../utils.js';
import { useInView, useCountUp, prefersReducedMotion } from '../hooks.js';
import { Reveal, Metric } from '../components/common.jsx';
import { rmIcon, rmDoneIcon } from '../components/roadmapIcons.jsx';

export function DeadlinePanel({ user, savedPolicies = [], onToggleSavedPolicy, onLoginClick }) {
  // Backend: GET /api/announcements → 마감 임박 공고 (DB의 실제 공고)
  const { data: deadlines, source } = useApi('/announcements?limit=4', DEADLINES, (raw) =>
    (raw.announcements || []).slice(0, 4).map((x) => ({
      id: String(x.id),
      policyId: x.policyId,
      dday: x.dday === null || x.dday === undefined ? '상시' : `D-${x.dday}`,
      tone: x.dday <= 7 ? 'urgent' : x.dday <= 30 ? 'soon' : 'normal',
      title: x.title,
      meta: [x.region, x.industry, x.benefit].filter(Boolean).join(' · ').slice(0, 60),
      url: x.sourceUrl,
    }))
  );

  // 저장은 마이페이지와 같은 App 상태·서버(saved_policies)를 쓴다. 공고 id가 아니라 정책 id로 저장한다.
  const [err, setErr] = useState('');
  const savedIds = new Set(savedPolicies.map((p) => p.policyId));
  // 목데이터(DEADLINES)에는 정책 id가 없어 저장할 수 없다.
  const canSave = source === 'api';
  const toggle = (policyId) => {
    if (!user) {
      onLoginClick && onLoginClick();
      return;
    }
    setErr('');
    onToggleSavedPolicy({ policyId }).catch(() =>
      setErr('저장 상태를 바꾸지 못했어요. 잠시 후 다시 시도해 주세요.')
    );
  };

  return (
    <aside className="panel" aria-labelledby="panel-title">
      <div className="panel__head">
        <h2 id="panel-title" className="panel__title">마감 임박 공고</h2>
        <span className="panel__more">전체 보기</span>
      </div>
      <ul className="deadlines">
        {deadlines.map((item) => (
          <li key={item.id} className="deadline">
            <span className={`deadline__dday u-num is-${item.tone}`}>{item.dday}</span>
            <div>
              <p className="deadline__title">{item.title}</p>
              <p className="deadline__meta">{item.meta}</p>
            </div>
            {canSave && (
              <button className="star" type="button" aria-pressed={savedIds.has(item.policyId)}
                aria-label={`${item.title} 관심 공고 저장`} onClick={() => toggle(item.policyId)}>
                {savedIds.has(item.policyId) ? '★' : '☆'}
              </button>
            )}
          </li>
        ))}
      </ul>
      <p className="panel__foot">
        {err ||
          (savedPolicies.length > 0
          ? `관심 공고 ${savedPolicies.length}건 저장됨 · 마감 3일 전 알림을 보내드려요`
          : '★ 를 눌러 관심 공고를 저장하면 마감 알림을 받아요')}
      </p>
    </aside>
  );
}

export function Hero({ onNavigate, user, savedPolicies, onToggleSavedPolicy, onLoginClick }) {
  // Backend: GET /api/stats → 실제 모집 중 공고 수
  const { data: stats, source: statsSrc } = useApi('/stats', null, (raw) => raw);
  const total = (stats && stats.openAnnouncements) || 1842;
  const count = useCountUp(total, true);
  let wi = 0;
  return (
    <section className="hero" id="top">
      <div className="glow glow--blue" aria-hidden="true" />
      <div className="glow glow--violet" aria-hidden="true" />
      <div className="wrap hero__inner">
        <div>
          <p className="badge">
            <span className="badge__dot" aria-hidden="true" />
            매일 09:00 자동 갱신
          </p>
          <p className="figure u-num">
            {count.toLocaleString()}
            <span className="figure__unit">건 모집 중</span>
          </p>
          <h1 className="title">
            {HERO_TITLE.map((line, li) => (
              <React.Fragment key={li}>
                {line.map((w) => (
                  <span className="w" style={{ '--i': wi++ }} key={w + wi}>
                    {w}
                    {' '}
                  </span>
                ))}
                {li === 0 && <br />}
              </React.Fragment>
            ))}
          </h1>
          <p className="lede">
            중앙부처 · 지자체 · 공공기관 공고를 모아 내 조건에 맞는 것만 골라
            드립니다. 세액 감면 대상 여부와 신고 일정까지 함께요.
          </p>
          <div className="hero__actions">
            <a className="btn btn--primary btn--lg" href="#onboarding">내 조건으로 찾기</a>
            <button className="btn btn--ghost btn--lg" type="button" onClick={() => onNavigate('roadmap')}>
              창업 로드맵 보기
            </button>
          </div>
          <dl className="stats">
            <div className="stat">
              <dt className="stat__label">수집 정책</dt>
              <dd className="stat__value u-num">
                {stats ? `${stats.policies.toLocaleString()}건` : '2,907건'}
              </dd>
            </div>
            <div className="stat">
              <dt className="stat__label">세법 조문</dt>
              <dd className="stat__value u-num">
                {stats ? `${stats.taxDocuments.toLocaleString()}건` : '4,459건'}
              </dd>
            </div>
            <div className="stat">
              <dt className="stat__label">최대 세액 감면</dt>
              <dd className="stat__value stat__value--pos u-num">
                {stats ? `${stats.maxReductionRate}%` : '100%'}
              </dd>
            </div>
          </dl>
        </div>
        <DeadlinePanel
          user={user}
          savedPolicies={savedPolicies}
          onToggleSavedPolicy={onToggleSavedPolicy}
          onLoginClick={onLoginClick}
        />
      </div>
    </section>
  );
}

/* ---------- 홈 2: 창업 일정 달력 ---------- */
/** 홈 캘린더는 전부가 아니라 "중요 일정"만: 세금 신고일·내 일정 전부 + 가까운 지원사업 마감 몇 개 */
/**
 * Backend 의 /api/calendar 응답을 { 'YYYY-MM-DD': [{id,type,title,note,mine}] } 로 변환.
 * 서버는 dueDate·eventType(TAX/POLICY/USER)로 내려주고, 목데이터는 date·type을 쓴다.
 */

export function Calendar({ compact, events: providedEvents }) {
  const today = new Date();
  const todayKey = `${today.getFullYear()}-${pad2(today.getMonth() + 1)}-${pad2(today.getDate())}`;
  const [cur, setCur] = useState({ y: today.getFullYear(), m: today.getMonth() });
  const [sel, setSel] = useState(todayKey);

  // 홈에서는 예시 일정을, 서비스 내부 화면에서는 전달받은 실제 일정을 표시한다.
  const events = providedEvents || CAL_EVENTS;

  const startDow = new Date(cur.y, cur.m, 1).getDay();
  const daysInMonth = new Date(cur.y, cur.m + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < startDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(null);

  const monthPrefix = `${cur.y}-${pad2(cur.m + 1)}`;
  const monthCount = Object.keys(events).filter((k) => k.startsWith(monthPrefix)).length;
  const shift = (delta) => {
    const nd = new Date(cur.y, cur.m + delta, 1);
    setCur({ y: nd.getFullYear(), m: nd.getMonth() });
  };
  const selEvents = events[sel] || [];
  const [sy, sm, sd] = sel.split('-').map(Number);
  const selLabel = `${sm}월 ${sd}일 (${WEEKDAYS[new Date(sy, sm - 1, sd).getDay()]})`;

  return (
    <div className={'cal' + (compact ? ' cal--compact' : '')} role="group" aria-label="창업 일정 달력">
      <div className="cal__head">
        <h3 className="cal__title">창업 일정</h3>
        <div className="cal__nav">
          <button type="button" onClick={() => shift(-1)} aria-label="이전 달">‹</button>
          <span className="cal__month">{cur.y}.{pad2(cur.m + 1)}</span>
          <button type="button" onClick={() => shift(1)} aria-label="다음 달">›</button>
        </div>
      </div>
      <p className="cal__sub">
        이번 달 주요 일정 {monthCount}건 · 전체 일정은 마이페이지에서 확인하세요
      </p>
      <div className="cal__grid">
        {WEEKDAYS.map((w, i) => (
          <div key={w} className={'cal__dow' + (i === 0 ? ' cal__dow--sun' : '')}>{w}</div>
        ))}
        {cells.map((d, i) => {
          if (!d) return <div key={`e${i}`} className="cal__day cal__day--out" />;
          const k = dayKey(cur.y, cur.m, d);
          const types = [...new Set((events[k] || []).map((e) => e.type))];
          const isSel = k === sel;
          return (
            <button
              key={k}
              type="button"
              className={
                'cal__day' +
                (isSel ? ' cal__day--sel' : '') +
                (k === todayKey && !isSel ? ' cal__day--today' : '')
              }
              aria-pressed={isSel}
              onClick={() => setSel(k)}
            >
              {d}
              {types.length > 0 && (
                <span className="cal__dot">
                  {types.map((t) => <i key={t} className={t === 'tax' ? 't-tax' : 't-policy'} />)}
                </span>
              )}
            </button>
          );
        })}
      </div>
      <div className="cal__legend">
        <span><i className="t-tax" /> 세금 신고</span>
        <span><i className="t-policy" /> 지원사업</span>
      </div>
      {!compact && (
        <div className="cal__events">
          <h4>{selLabel} 일정</h4>
          {selEvents.length === 0 ? (
            <p className="cal__empty">등록된 일정이 없어요.</p>
          ) : (
            /* 목록이 길어지면 달력이 한 화면을 넘어가므로 2건까지만 보여준다 */
            <React.Fragment>
              {selEvents.slice(0, 2).map((e) => (
                <div key={e.title} className="cal__ev">
                  <i className={e.type === 'tax' ? 't-tax' : 't-policy'} />
                  <div>
                    <b>{e.title}</b>
                    <span>{e.note}</span>
                  </div>
                </div>
              ))}
              {selEvents.length > 2 && (
                <p className="cal__more">외 {selEvents.length - 2}건 · 전체는 마이페이지에서 확인하세요</p>
              )}
            </React.Fragment>
          )}
        </div>
      )}
    </div>
  );
}

export function Schedule() {
  return (
    <section className="sec">
      <div className="wrap stmt__grid">
        <Reveal><Calendar /></Reveal>
        <div>
          <Reveal as="p" className="eyebrow">창업 일정 관리</Reveal>
          <h2 className="stmt__head">
            <Reveal as="span" className="stmt__line">마감일을 놓치지 않게</Reveal>
            <Reveal as="span" className="stmt__line" delay={120}>
              <em>한 캘린더</em>로 관리합니다
            </Reveal>
          </h2>
          <Reveal as="p" className="stmt__sub" delay={200}>
            지원사업 접수 마감일과 세금 신고일을 한 달력에 모았어요.
            관심 공고를 저장하면 마감 3일 전에 알림을 보내드립니다.
          </Reveal>
          <Reveal as="ul" className="stmt__mini" delay={260}>
            <li><b>D-8</b><span>청년창업사관학교 15기 마감<em>중소벤처기업진흥공단</em></span></li>
            <li><b>D-17</b><span>부가세 2기 예정신고<em>홈택스 전자신고</em></span></li>
            <li><b>D-22</b><span>서울 청년창업 임차보증금 지원 마감<em>서울시</em></span></li>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

/* ---------- 홈 3: AI 대화 ---------- */
// 홈 화면 대화창의 시작 질문 — 왼쪽 태그(chat__tag) 4개와 짝을 맞춘다

export function ChatDemo() {
  // 한 번 화면에 들어오면 끝까지 재생하고 그대로 유지 (스크롤해도 리셋 안 함)
  const [ref, inView] = useInView({ threshold: 0.25 });
  const [shown, setShown] = useState(0);
  const [typing, setTyping] = useState(false);
  const [extra, setExtra] = useState([]);
  const [draft, setDraft] = useState('');
  const bodyRef = useRef(null);

  useEffect(() => {
    if (!inView) return;
    if (prefersReducedMotion) {
      setShown(CHAT.length);
      return;
    }
    if (shown >= CHAT.length) return;
    const next = CHAT[shown];
    let t;
    if (next.role === 'ai') {
      setTyping(true);
      t = setTimeout(() => {
        setTyping(false);
        setShown((s) => s + 1);
      }, 900);
    } else {
      t = setTimeout(() => setShown((s) => s + 1), 520);
    }
    return () => clearTimeout(t);
  }, [inView, shown]);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [shown, typing, extra]);

  const send = (e) => {
    e.preventDefault();
    const q = draft.trim();
    if (!q) return;
    setDraft('');
    setExtra((x) => [...x, { role: 'user', text: q }]);
    setTimeout(() => {
      setExtra((x) => [
        ...x,
        { role: 'ai', text: '실제 서비스에서는 국세청 해석사례와 관련 법령을 인용해 답변하고, 필요한 일정을 캘린더에 등록해 드려요.' },
      ]);
    }, 700);
  };

  const msgs = [...CHAT.slice(0, shown), ...extra];

  return (
    <section className="sec sec--alt">
      <div className="wrap chat__grid">
        <div>
          <Reveal as="p" className="eyebrow">AI 어시스턴트</Reveal>
          <Reveal as="h2" className="chat__title" delay={80}>
            대화하듯 물어보면<br />창업과 세금 업무가 정리됩니다
          </Reveal>
          <Reveal as="p" className="chat__lead" delay={160}>
            지원사업 탐색, 사업자 유형 판단, 세액감면 여부, 신고 일정 등록까지 —
            한 번의 대화로 이어서 처리할 수 있어요.
          </Reveal>
          <Reveal className="chat__tags" delay={220}>
            <span className="chat__tag">지원사업 매칭</span>
            <span className="chat__tag">세액감면 판정</span>
            <span className="chat__tag">신고 일정 등록</span>
            <span className="chat__tag">경비처리 상담</span>
          </Reveal>
        </div>

        <Reveal>
          <div className="chatbox" ref={ref}>
            <div className="chatbox__bar">
              <span className="chatbox__ava" aria-hidden="true">ON</span>
              <span className="chatbox__who">
                <b>창업ON 어시스턴트</b>
                <span>온라인 · 보통 몇 초 안에 응답</span>
              </span>
            </div>
            <div className="chatbox__body" ref={bodyRef}>
              {msgs.map((m, i) => (
                <div key={i} className={`msg msg-in msg--${m.role}`}>{m.text}</div>
              ))}
              {typing && (
                <div className="typing" aria-label="입력 중">
                  <i /><i /><i />
                </div>
              )}
            </div>
            <form className="chatbox__input" onSubmit={send}>
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="메시지를 입력해 보세요"
                aria-label="메시지 입력"
              />
              <button type="submit">전송</button>
            </form>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/* ---------- 홈 4: 창업 A-Z 로드맵 ---------- */

export function Roadmap() {
  const [ref, inView] = useInView({ threshold: 0.2 }, true);
  const on = inView || prefersReducedMotion;
  return (
    <section className="sec">
      <div className="wrap">
        <Reveal as="p" className="eyebrow">창업 A → Z</Reveal>
        <Reveal as="h2" className="sec__title" delay={80}>
          아이디어부터 스케일업까지
        </Reveal>
        <div className={'rz' + (on ? ' is-in' : '')} ref={ref}>
          <div className="rz__row">
            {ROADMAP.map((s, i) => (
              <React.Fragment key={s.k}>
                {i > 0 && (
                  <div className="rz__sep" aria-hidden="true" style={{ '--d': `${i * 160 + 80}ms` }}>›</div>
                )}
                <div
                  className={'rz__step' + (s.accent ? ' rz__step--accent' : '')}
                  style={{ '--d': `${i * 160 + 150}ms` }}
                >
                  <span className="rz__ico">{rmIcon(s.k)}</span>
                  <span className="rz__phase">{s.phase}</span>
                  <span className="rz__t">{s.t}</span>
                </div>
              </React.Fragment>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

export function Closing({ onStart, user }) {
  return (
    <section className="sec">
      <Reveal className="wrap closing">
        <div className="closing__stats">
          {METRICS.map((m, i) => (
            <Metric key={m.label} {...m} delay={i * 70} />
          ))}
        </div>
        <div className="closing__cta">
          <p className="eyebrow">지금 창업ON에서</p>
          <h2>지금, 내 조건으로 시작하세요</h2>
          <button className="btn btn--primary btn--lg" type="button" onClick={onStart}>
            {user ? '마이페이지 바로가기' : '로그인'}
          </button>
        </div>
      </Reveal>
    </section>
  );
}

export function Home({ onNavigate, user, savedPolicies, onToggleSavedPolicy, onLoginClick }) {
  return (
    <main className="home-flow">
      <Hero
        onNavigate={onNavigate}
        user={user}
        savedPolicies={savedPolicies}
        onToggleSavedPolicy={onToggleSavedPolicy}
        onLoginClick={onLoginClick}
      />
      <Schedule />
      <ChatDemo />
      <Roadmap />
      <Closing onStart={() => onNavigate('mypage')} user={user} />
    </main>
  );
}

/* ---------- App ---------- */
// 저장한 공고는 화면을 옮겨도 유지돼야 해서 브라우저에 남긴다
