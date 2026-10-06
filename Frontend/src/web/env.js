// 반응형 웹앱에서 실행 중인지. web/main.jsx가 <html>에 is-web을 붙인다.
// 공통 화면 부품이 웹앱에서만 동작을 조금 바꿀 때 쓴다(기본 페이지 동작은 그대로).
export const isWebApp = () => typeof document !== 'undefined' && document.documentElement.classList.contains('is-web');

// 홈 '오늘 챙길 일' 카드 → 다른 화면으로 넘길 값(예: 열 공고, 지출 필터). 화면 이동은 App이 하므로
// 잠깐 sessionStorage에 두고, 도착한 화면이 한 번 꺼내 쓴다. 30초가 지나면 무시한다.
const HANDOFF_KEY = 'changeup:web-handoff';
export function setHandoff(page, data) {
  try {
    sessionStorage.setItem(HANDOFF_KEY, JSON.stringify({ page, data, at: Date.now() }));
  } catch {
    /* 저장할 수 없으면 그냥 화면만 이동한다 */
  }
}
export function takeHandoff(page) {
  try {
    const v = JSON.parse(sessionStorage.getItem(HANDOFF_KEY) || 'null');
    if (!v || v.page !== page) return null;
    sessionStorage.removeItem(HANDOFF_KEY);
    return Date.now() - v.at > 30000 ? null : v.data;
  } catch {
    return null;
  }
}
