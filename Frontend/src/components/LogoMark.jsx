import React from 'react';

// 창업ON 로고 마크: 얇은 원 테두리 안에 오른쪽이 열린 "C", 그 열린 자리에 초록 점(ON 표시).
// 원 테두리와 C는 홈페이지 블루 토큰(--blue)을 따라가므로 라이트·다크 모드에서 같이 바뀐다.
export function LogoMark() {
  return (
    <span className="brand__mark" aria-hidden="true">
      <svg viewBox="0 0 64 64" focusable="false">
        <circle cx="32" cy="32" r="30.65" fill="none" strokeWidth="2.7" style={{ stroke: 'var(--blue)' }} />
        <path
          d="M39.87 23.73A11.6 11.6 0 1 0 39.87 40.27"
          fill="none"
          strokeWidth="5.6"
          strokeLinecap="round"
          style={{ stroke: 'var(--blue)' }}
        />
        <circle cx="44.1" cy="32" r="4.2" fill="#34b36a" />
      </svg>
    </span>
  );
}

// 로고 옆 글씨: "CHANGUP"은 중간 굵기, "ON"은 굵게. 글자색은 --brand-ink(라이트 검정, 다크 밝은색).
export function BrandWord() {
  return (
    <span className="brand__word">
      CHANGUP <b>ON</b>
    </span>
  );
}
