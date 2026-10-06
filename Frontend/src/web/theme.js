// 반응형 웹앱(/web.html) 테마: '시스템 설정 따르기(system) · 라이트 · 다크' 하나의 값만 저장한다.
// 홈 헤더의 테마 아이콘과 마이페이지 > 설정의 '테마 변경'이 이 값을 함께 쓰므로 한쪽에서 바꾸면 다른 쪽도 따라 바뀐다.
import { useEffect, useState } from 'react';

const KEY = 'changeup:web-theme';
const EVENT = 'changeup:theme-change';
const DARK_QUERY = '(prefers-color-scheme: dark)';

export const THEME_OPTIONS = [
  { value: 'system', label: '시스템 설정 따르기' },
  { value: 'light', label: '라이트' },
  { value: 'dark', label: '다크' },
];

export function getThemePref() {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'light' || saved === 'dark' || saved === 'system') return saved;
  } catch {
    /* 저장소를 쓸 수 없으면 시스템 설정 */
  }
  return 'system';
}

function systemIsDark() {
  return typeof window !== 'undefined' && !!window.matchMedia && window.matchMedia(DARK_QUERY).matches;
}

/** 지금 화면에 실제로 적용된 테마('light' | 'dark') */
export function effectiveTheme(pref = getThemePref()) {
  if (pref === 'system') return systemIsDark() ? 'dark' : 'light';
  return pref;
}

/** data-theme 속성과 설치 앱 상태바 색을 맞춘다. system이면 속성을 지워 CSS의 prefers-color-scheme을 따른다. */
export function applyThemePref(pref = getThemePref()) {
  const root = document.documentElement;
  if (pref === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', pref);
  const color = effectiveTheme(pref) === 'dark' ? '#0d101e' : '#f4f6fd';
  document.querySelectorAll('meta[name="theme-color"]').forEach((m) => m.setAttribute('content', color));
}

export function setThemePref(pref) {
  try {
    localStorage.setItem(KEY, pref);
  } catch {
    /* 저장하지 못해도 이번 화면에는 적용한다 */
  }
  applyThemePref(pref);
  window.dispatchEvent(new CustomEvent(EVENT, { detail: pref }));
}

/** 저장된 선택과 실제 적용 테마를 함께 돌려준다. 다른 곳에서 바꾸거나 시스템 설정이 바뀌면 다시 그린다. */
export function useThemePref() {
  const [state, setState] = useState(() => ({ pref: getThemePref(), effective: effectiveTheme() }));
  useEffect(() => {
    const sync = () => setState({ pref: getThemePref(), effective: effectiveTheme() });
    const media = window.matchMedia ? window.matchMedia(DARK_QUERY) : null;
    const onSystem = () => {
      if (getThemePref() === 'system') applyThemePref('system');
      sync();
    };
    window.addEventListener(EVENT, sync);
    window.addEventListener('storage', sync); // 다른 탭에서 바꾼 경우
    if (media) media.addEventListener('change', onSystem);
    return () => {
      window.removeEventListener(EVENT, sync);
      window.removeEventListener('storage', sync);
      if (media) media.removeEventListener('change', onSystem);
    };
  }, []);
  return [state.pref, state.effective, setThemePref];
}
