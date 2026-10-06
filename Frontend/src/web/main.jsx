// 반응형 웹앱 진입점(/web.html). 기존 PC 화면(홈 · 기능 페이지 · 마이페이지)을 모든 폭에서 쓰고,
// html.is-web 아래에서만 동작하는 web.css로 휴대폰 · 태블릿 폭의 배치를 바꾼다.
import { createRoot } from 'react-dom/client';
import App from '../App.jsx';
import '../styles.css';
import './web.css';
import { applyThemePref } from './theme.js';

document.documentElement.classList.add('is-web');

// 저장된 테마 선택(시스템 · 라이트 · 다크)을 첫 화면을 그리기 전에 적용한다(web/theme.js).
applyThemePref();
createRoot(document.getElementById('root')).render(<App variant="web" />);
