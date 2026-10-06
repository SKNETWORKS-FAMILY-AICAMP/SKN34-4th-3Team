// 반응형 웹앱 휴대폰 폭 전용 하단 탭바. 768px보다 넓으면 web.css에서 숨긴다.
// 사업계획서는 입력이 많은 화면이라 탭에서 빼고 메뉴(햄버거)로 들어간다.
import React from 'react';

const ICON = {
  home: 'M4 10.5 12 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5.5h-5V20H5a1 1 0 0 1-1-1z',
  roadmap: 'M5 19c0-3 2-4 4.5-4.5S14 13 14 10s-2.5-4-5-4M14 10h5M16.5 7.5 19 10l-2.5 2.5M5 19h.01',
  tax: 'M7 4h10a1 1 0 0 1 1 1v15l-3-2-3 2-3-2-3 2V5a1 1 0 0 1 1-1zM9 9h6M9 12.5h6',
  expenses: 'M4 7.5A1.5 1.5 0 0 1 5.5 6h13A1.5 1.5 0 0 1 20 7.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 16.5zM4 10h16M7.5 14.5h3',
  gov: 'M5 9.5 12 5l7 4.5M6.5 10v7M10 10v7M14 10v7M17.5 10v7M4.5 19.5h15',
  mypage: 'M12 12a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM5 20c.8-3.4 3.6-5.5 7-5.5s6.2 2.1 7 5.5',
};

const TABS = [
  { key: 'home', label: '홈' },
  { key: 'roadmap', label: '로드맵' },
  { key: 'tax', label: '세무' },
  { key: 'expenses', label: '지출' },
  { key: 'gov', label: '공고' },
  { key: 'mypage', label: '마이' },
];

export function WebTabBar({ current, onNavigate }) {
  return (
    <nav className="wtab" aria-label="주요 기능">
      {TABS.map((t) => {
        const on = current === t.key;
        return (
          <button key={t.key} type="button" className={'wtab__item' + (on ? ' is-on' : '')}
            aria-current={on ? 'page' : undefined} onClick={() => { if (!on) onNavigate(t.key); }}>
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d={ICON[t.key]} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>{t.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
