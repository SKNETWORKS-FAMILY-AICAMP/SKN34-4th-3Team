// ============================================================
// Backend(FastAPI) 연동 레이어
//
//   Frontend(:5173) --/api--> Backend(:8000) --> DB(Postgres :5432)
//                                    └--> LLM 서비스(:8001)
//
// - 개발 서버가 /api 를 http://localhost:8000 으로 프록시한다 (vite.config.js)
// - Backend 가 꺼져 있으면 각 호출이 실패 → fallback(화면의 목데이터) 사용
// - 엔드포인트 규격: Docs/Design/API_SPEC.md
// ============================================================

import { useEffect, useState } from 'react';

const BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/+$/, '');

const TOKEN_KEY = 'changeup.accessToken';

/** 로그인 토큰. 없으면 null. */
export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null; // 사생활 보호 모드 등에서 접근이 막힐 수 있다
  }
}

function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* 저장 못 해도 이번 세션은 동작한다 */
  }
}

/** 토큰이 있으면 Bearer로 싣는다. 공개 엔드포인트는 없어도 그대로 동작한다. */
function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** 만료·무효 토큰으로 계속 실패하지 않도록 401이면 지운다. */
function handleStatus(res, path) {
  if (res.status === 401) setToken(null);
  if (!res.ok) {
    // 호출부가 문자열을 뒤지지 않고 상태 코드로 분기할 수 있게 실어 보낸다.
    const err = new Error(`HTTP ${res.status} ${path}`);
    err.status = res.status;
    throw err;
  }
}

function qs(params) {
  const sp = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '' && v !== '전체') sp.append(k, v);
  });
  const s = sp.toString();
  return s ? `?${s}` : '';
}

/** GET. 실패(네트워크·비2xx·타임아웃)하면 throw. */
export async function apiGet(path, { signal, timeout = 6000 } = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeout);
  const relay = () => ctl.abort();
  if (signal) signal.addEventListener('abort', relay);
  try {
    const res = await fetch(BASE + path, {
      signal: ctl.signal,
      headers: { Accept: 'application/json', ...authHeaders() },
    });
    handleStatus(res, path);
    return await res.json();
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener('abort', relay);
  }
}

/** POST(JSON). 실패하면 throw. */
export async function apiPost(path, body, { signal, timeout = 30000 } = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeout);
  const relay = () => ctl.abort();
  if (signal) signal.addEventListener('abort', relay);
  try {
    const res = await fetch(BASE + path, {
      method: 'POST',
      signal: ctl.signal,
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...authHeaders() },
      body: JSON.stringify(body || {}),
    });
    handleStatus(res, path);
    return await res.json();
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener('abort', relay);
  }
}

/** PUT(JSON). 실패하면 throw. */
export async function apiPut(path, body, { signal, timeout = 10000 } = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeout);
  const relay = () => ctl.abort();
  if (signal) signal.addEventListener('abort', relay);
  try {
    const res = await fetch(BASE + path, {
      method: 'PUT',
      signal: ctl.signal,
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...authHeaders() },
      body: JSON.stringify(body || {}),
    });
    handleStatus(res, path);
    return await res.json();
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener('abort', relay);
  }
}

/** DELETE. 실패(네트워크·비2xx·타임아웃)하면 throw. */
export async function apiDelete(path, { signal, timeout = 10000 } = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeout);
  const relay = () => ctl.abort();
  if (signal) signal.addEventListener('abort', relay);
  try {
    const res = await fetch(BASE + path, {
      method: 'DELETE',
      signal: ctl.signal,
      headers: { Accept: 'application/json', ...authHeaders() },
    });
    handleStatus(res, path);
    return await res.json();
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener('abort', relay);
  }
}

/* ---------- 엔드포인트 헬퍼 ---------- */
/* ---------- 인증 ---------- */

/** 로그인. 성공하면 토큰을 저장하고 사용자 정보를 돌려준다. */
export async function login(email, password) {
  const r = await apiPost('/auth/login', { email, password });
  setToken(r.accessToken);
  return r; // { accessToken, userId, name, role }
}

/** 회원가입 후 곧바로 로그인한다. */
export async function signup(email, password, name) {
  await apiPost('/auth/signup', { email, password, name });
  return login(email, password);
}

export function logout() {
  setToken(null);
}

/**
 * 저장된 토큰으로 사용자 복원. 토큰이 없거나 무효(401)면 null.
 * Backend 미실행·타임아웃은 "세션이 끝났다"가 아니므로 throw 해서 호출부가 구분하게 둔다.
 */
export async function me() {
  if (!getToken()) return null;
  try {
    return await apiGet('/users/me');
  } catch (e) {
    if (e && e.status === 401) return null; // handleStatus가 토큰을 이미 지웠다
    throw e;
  }
}

export const api = {
  login,
  signup,
  logout,
  me,
  updateMe: (body, opt) => apiPut('/users/me', body, opt),
  businessProfile: (opt) => apiGet('/users/me/business-profile', opt),
  updateBusinessProfile: (body, opt) => apiPut('/users/me/business-profile', body, opt),
  stats: (opt) => apiGet('/stats', opt),
  announcements: (params, opt) => apiGet('/announcements' + qs(params), opt),
  policies: (params, opt) => apiGet('/policies' + qs(params), opt),
  policy: (id, opt) => apiGet(`/policies/${id}`, opt),
  recommendations: (params, opt) => apiGet('/policies/recommendations' + qs(params), opt),
  savedPolicies: (opt) => apiGet('/policies/saved', opt),
  savePolicy: (policyId, opt) => apiPost(`/policies/${policyId}/save`, {}, opt),
  unsavePolicy: (policyId, opt) => apiDelete(`/policies/${policyId}/save`, opt),
  calendar: (params, opt) => apiGet('/calendar' + qs(params), opt),
  calendarCreate: (body, opt) => apiPost('/calendar', body, opt),
  calendarDelete: (eventId, opt) => apiDelete(`/calendar/${eventId}`, opt),
  calendarUpcoming: (params, opt) => apiGet('/calendar/upcoming' + qs(params), opt),
  taxSchedule: (params, opt) => apiGet('/tax/schedule' + qs(params), opt),
  taxDocuments: (params, opt) => apiGet('/tax/documents' + qs(params), opt),
  taxCheck: (body, opt) => apiPost('/tax/tax-reduction/check', body, opt),
  // 세무 멀티홉은 Backend가 LLM 응답을 최대 120초 기다린다.
  // 공통 POST 기본 제한(30초)으로 먼저 중단하지 않도록 채팅에만 여유를 둔다.
  chat: (body, opt) => apiPost('/chat/messages', body, {
    timeout: ['tax', 'expense', 'saving'].includes(body?.category) ? 135000 : 60000,
    ...opt,
  }),
  chatHistory: (category, opt) => apiGet('/chat/messages' + qs({ category }), opt),
  clearChat: (category, opt) => apiDelete('/chat/messages' + qs({ category }), opt),
  // 대화방 하나만 삭제 — 그 방에 속한 메시지 id들만 지운다(다른 방은 그대로).
  // ids가 비면 qs()가 파라미터를 빼서 "전체 삭제" 요청이 되므로 보내지 않고 실패로 돌린다.
  deleteMessages: (ids, opt) =>
    ids && ids.length
      ? apiDelete('/chat/messages' + qs({ ids: ids.join(',') }), opt)
      : Promise.reject(new Error('deleteMessages: ids가 비어 있음')),
  chatSources: (messageId, opt) => apiGet(`/chat/messages/${messageId}/sources`, opt),
  // 캐시가 없으면 LLM이 즉시 요약을 생성하므로 일반 GET보다 긴 제한 시간을 둔다.
  announcementSummary: (announcementId, opt) => apiGet(
    `/announcements/${announcementId}/summary`,
    { timeout: 50000, ...opt }
  ),
  summarizeAnnouncement: (body, opt) => apiPost('/announcements/summary', body, opt),
};

/**
 * 백엔드에서 데이터를 받아오되, 실패하면 fallback(목데이터)을 쓴다.
 *
 * @param {string}   path      예: '/policies/recommendations'
 * @param {*}        fallback  백엔드 없을 때 값 (모듈 상수 — 참조 고정 필요)
 * @param {Function} [map]     원본 응답 → 화면이 기대하는 형태
 * @returns {{ data:*, loading:boolean, source:'api'|'fallback', error:string }}
 */
export function useApi(path, fallback, map = (x) => x) {
  const [state, setState] = useState({
    data: fallback,
    loading: true,
    source: 'fallback',
    error: '',
  });

  useEffect(() => {
    let alive = true;
    const ctl = new AbortController();
    apiGet(path, { signal: ctl.signal })
      .then((raw) => {
        if (!alive) return;
        let mapped;
        try {
          mapped = map(raw);
        } catch (e) {
          setState({ data: fallback, loading: false, source: 'fallback', error: 'map error' });
          return;
        }
        // 비어 있는 응답도 정상 응답이다. 예전에는 목데이터로 바꿔치기해서
        // "결과 없음"과 "백엔드 없음"을 구분할 수 없었다. 실패는 catch가 처리한다.
        setState({ data: mapped, loading: false, source: 'api', error: '' });
      })
      .catch((e) => {
        if (alive) {
          setState({ data: fallback, loading: false, source: 'fallback', error: String(e.message || e) });
        }
      });
    return () => {
      alive = false;
      ctl.abort();
    };
    // fallback/map 은 모듈 상수라 참조 고정 → path 만 의존
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);

  return state;
}

/** 백엔드 연결 여부 배지에 쓸 상태 */
export function useBackendStatus() {
  const [ok, setOk] = useState(null); // null=확인중, true/false
  useEffect(() => {
    let alive = true;
    apiGet('/stats', { timeout: 4000 })
      .then(() => alive && setOk(true))
      .catch(() => alive && setOk(false));
    return () => {
      alive = false;
    };
  }, []);
  return ok;
}
