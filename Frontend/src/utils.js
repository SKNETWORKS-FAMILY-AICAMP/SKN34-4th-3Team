// 순수 로직 헬퍼(날짜, localStorage 저장, 판정 등). JSX 없음.
import { GOV_LISTINGS, USER_STORE_KEY } from './constants.js';

export const pad2 = (n) => String(n).padStart(2, '0');

export const dayKey = (y, m, d) => `${y}-${pad2(m + 1)}-${pad2(d)}`;

// 메인(홈) 화면 달력은 둘러보기용 예시 일정만 보여 준다.
// 마이페이지 달력(서버에 저장되는 내 일정)과는 일부러 연동하지 않는다.
// 언제 열어도 보이도록 날짜는 "이번 달" 기준으로 잡는다.

export const CAL_EVENTS = (() => {
  const now = new Date();
  const k = (d) => dayKey(now.getFullYear(), now.getMonth(), d);
  return {
    [k(10)]: [{ type: 'tax', title: '원천세 신고·납부', note: '전월 급여 지급분' }],
    [k(17)]: [{ type: 'policy', title: '청년창업사관학교 15기 마감', note: '중소벤처기업진흥공단' }],
    [k(25)]: [{ type: 'tax', title: '부가세 예정신고', note: '홈택스 전자신고' }],
  };
})();

export const inputStyle = {
  width: '100%', padding: '11px 12px', font: 'inherit', fontSize: 13.5, color: 'var(--ink)',
  background: 'var(--ground)', border: '1px solid var(--line-strong)', borderRadius: 10,
};

export const linkBtn = {
  border: 0, background: 'transparent', padding: 0, font: 'inherit', fontWeight: 700,
  color: 'var(--blue-deep)', cursor: 'pointer', textDecoration: 'underline',
};

export const fieldLabel = { display: 'block', marginBottom: 5, fontSize: 12, fontWeight: 600, color: 'var(--ink-soft)' };

export const socialBtn = {
  width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
  padding: '11px 12px', border: 0, borderRadius: 11, fontSize: 13.5, fontWeight: 700, cursor: 'pointer',
};

// Backend가 시드하는 데모 계정 (core/config.py DEMO_EMAIL/DEMO_PASSWORD와 동일)

/** 저장 시각을 'YYYY-MM-DD' 로 줄인다. 형식이 예상과 달라도 앞 10글자는 건진다. */

export const dayKeyOf = (v) => {
  if (!v) return '';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return String(v).slice(0, 10);
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
};
/** 오늘·어제는 말로, 그보다 앞은 날짜로 적는다. */

export const dayLabel = (key) => {
  if (!key) return '날짜 미상';
  const now = new Date();
  const keyOf = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  if (key === keyOf(now)) return '오늘';
  if (key === keyOf(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1))) return '어제';
  const [yy, mm, dd] = key.split('-').map(Number);
  return yy === now.getFullYear() ? `${mm}월 ${dd}일` : `${yy}년 ${mm}월 ${dd}일`;
};

export const rowsToTurns = (rows) => {
  const out = [];
  (rows || []).forEach((row) => {
    out.push({ role: 'user', content: row.question });
    out.push({ role: 'assistant', content: row.answer });
  });
  return out;
};

/**
 * AI 답변은 마크다운으로 온다. 외부 라이브러리 없이 자주 쓰이는 문법만 추려
 * React 엘리먼트로 바꾼다(HTML 문자열을 넣지 않으므로 XSS 걱정이 없다).
 * 지원: ### 제목, - / 1. 목록, **굵게**, *기울임*, `코드`, 인용(>), 빈 줄 문단
 */

export function policyDday(end) {
  if (!end) return null;
  const [y, m, d] = String(end).split('-').map(Number);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((new Date(y, m - 1, d) - today) / 86400000);
}

export const policyDdayLabel = (n) => (n === null ? '상시' : n < 0 ? '마감' : `D-${n}`);

export const toPolicies = (raw) => raw.policies || [];

/* ===== AI 추천 공고 — 공고지원 AI가 조건 맞는 공고를 골라 저장 ===== */

export const progById = (id) => GOV_LISTINGS.find((g) => g.id === id);

export const ddayLabel = (g) => (g.dday >= 100 ? '상시' : `D-${g.dday}`);

/* 프로필 기준 매칭 점수 + 이유 */
/* 추천 공고 상세 (모달에서 보여 주는 데모 내용) */

export function scoreProgram(g, u) {
  let s = 40;
  const why = [];
  if (u && u.region && g.region !== '전국' && u.region.includes(g.region)) {
    s += 30;
    why.push(`${g.region} 지역 사업`);
  } else if (g.region === '전국') {
    s += 18;
    why.push('전국 대상');
  }
  if (/예비|초기/.test(g.target)) {
    s += 18;
    why.push(`${g.target} 창업자 대상`);
  }
  if (g.dday >= 100) {
    s += 6;
    why.push('상시 접수');
  } else if (g.dday <= 30) {
    s += 12;
    why.push(`마감 D-${g.dday}`);
  }
  if (g.type === '자금') {
    s += 8;
    why.push('사업화 자금');
  }
  return { score: Math.min(99, s), why };
}

export function eventsByDate(raw) {
  const map = {};
  (raw.events || []).forEach((e) => {
    const date = e.dueDate || e.date;
    if (!date) return;
    const kind = String(e.eventType || e.type || '').toLowerCase();
    const note = e.description || e.note || '';
    // 개인 일정은 서버에서 USER로 내려오므로 등록할 때 저장한 설명으로 세금/지원사업을 구분한다.
    const isTax = kind === 'tax' || (kind === 'user' && note === '세금 일정');
    (map[date] = map[date] || []).push({
      id: e.id,
      type: isTax ? 'tax' : 'policy',
      title: e.title,
      note,
      policyId: e.policyId ?? null,
      mine: !!e.mine,
    });
  });
  return map;
}

export function upcomingCalendarEvents(byDate, savedPolicies = [], now = new Date(), withinDays = 3) {
  const todayUtc = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  const savedIds = new Set(savedPolicies.map((p) => p.policyId));

  return Object.entries(byDate || {})
    .flatMap(([date, items]) => {
      const [y, m, d] = date.split('-').map(Number);
      const daysLeft = Math.round((Date.UTC(y, m - 1, d) - todayUtc) / 86400000);
      return items.map((item) => ({ ...item, date, daysLeft }));
    })
    .filter(
      (item) =>
        item.daysLeft >= 0 &&
        item.daysLeft <= withinDays &&
        (item.mine || item.type === 'tax' || (item.policyId != null && savedIds.has(item.policyId)))
    )
    .sort((a, b) => a.daysLeft - b.daysLeft || a.title.localeCompare(b.title, 'ko'));
}

export const loadStoredUser = () => {
  try {
    return JSON.parse(localStorage.getItem(USER_STORE_KEY) || 'null');
  } catch (e) {
    return null;
  }
};

// 창업 로드맵 체크리스트 — 서버(user_roadmap_progress)가 원본이다.
// 예전에 이 브라우저에 남긴 체크는 로그인 때 한 번 서버로 옮기고 지운다(App.jsx). 그 이관에만 쓴다.
// 키의 v2는 서버 version과 같은 의미다.

export const ROADMAP_KEY = (userId) => `changeup:roadmap-done:v2:${userId}`;

export const loadRoadmapDone = (userId) => {
  try {
    const obj = JSON.parse(localStorage.getItem(ROADMAP_KEY(userId)) || '{}');
    return obj && typeof obj === 'object' && !Array.isArray(obj) ? obj : {};
  } catch (e) {
    return {};
  }
};

export const clearLegacyRoadmapDone = (userId) => {
  try {
    localStorage.removeItem(ROADMAP_KEY(userId));
  } catch (e) {
    /* 저장 불가 환경은 무시 */
  }
};
