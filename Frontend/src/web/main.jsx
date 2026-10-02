// 반응형 웹앱 진입점(/web.html). 기존 PC 화면(홈 · 기능 페이지 · 마이페이지)을 모든 폭에서 쓰고,
// html.is-web 아래에서만 동작하는 web.css로 휴대폰 · 태블릿 폭의 배치를 바꾼다.
import { createRoot } from 'react-dom/client';
import App from '../App.jsx';
import '../styles.css';
import './web.css';

document.documentElement.classList.add('is-web');

// 다크 모드 선택을 기억한다(메뉴의 '다크 모드 전환'은 data-theme만 바꾸므로 그 변화를 저장 · 복원한다).
const THEME_KEY = 'changeup:web-theme';
try {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === 'dark' || saved === 'light') document.documentElement.setAttribute('data-theme', saved);
} catch {
  /* 저장소를 쓸 수 없으면 기본 테마 */
}
new MutationObserver(() => {
  const t = document.documentElement.getAttribute('data-theme');
  try {
    if (t) localStorage.setItem(THEME_KEY, t);
  } catch {
    /* 무시 */
  }
}).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
createRoot(document.getElementById('root')).render(<App variant="web" />);
