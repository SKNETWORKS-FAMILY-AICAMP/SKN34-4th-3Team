// 반응형 웹앱 로드맵 화면 헤더의 '로드맵 코치 채팅' 열기 · 닫기 버튼(휴대폰 폭에서만 보인다, web.css).
// 열려 있으면 파란 바탕에 '말풍선 + ×', 닫혀 있으면 빈 말풍선 아이콘을 보여 준다.
import React from 'react';

const BUBBLE = 'M5 5.5h14a1.5 1.5 0 0 1 1.5 1.5v8.5a1.5 1.5 0 0 1-1.5 1.5H10l-4.5 3.5V17H5a1.5 1.5 0 0 1-1.5-1.5V7A1.5 1.5 0 0 1 5 5.5z';
const DOTS = 'M8.5 11.25h.01M12 11.25h.01M15.5 11.25h.01';
const CLOSE = 'M9.5 8.75l5 5M14.5 8.75l-5 5';

export function CoachToggle({ open, onToggle }) {
  return (
    <button type="button" className={'wcoach' + (open ? ' is-open' : '')} onClick={onToggle}
      aria-pressed={open} aria-label={open ? '로드맵 코치 채팅 닫기' : '로드맵 코치 채팅 열기'}
      title={open ? '코치 채팅 닫기' : '코치 채팅 열기'}>
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d={BUBBLE} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
        <path d={open ? CLOSE : DOTS} fill="none" stroke="currentColor" strokeWidth={open ? 1.8 : 2.4} strokeLinecap="round" />
      </svg>
    </button>
  );
}
