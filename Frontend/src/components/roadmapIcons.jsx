import React from 'react';

export function rmIcon(k) {
  const p = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' };
  const paths = {
    A: <><path d="M9 18h6M10 21h4" {...p} /><path d="M12 3a6 6 0 0 0-4 10.4c.6.5 1 1.4 1 2.6h6c0-1.2.4-2.1 1-2.6A6 6 0 0 0 12 3Z" {...p} /></>,
    B: <><path d="M7 3h8l3 3v15H7z" {...p} /><path d="M15 3v4h4M10 12h5M10 16h5" {...p} /></>,
    C: <><circle cx="12" cy="12" r="8.5" {...p} /><path d="m8.5 12 2.5 2.5 4.5-5" {...p} /></>,
    D: <><circle cx="12" cy="12" r="8.5" {...p} /><path d="M12 7.5v9M9.7 9.7c0-1 1-1.6 2.3-1.6s2.3.6 2.3 1.6-1 1.3-2.3 1.5-2.3.6-2.3 1.6 1 1.6 2.3 1.6 2.3-.6 2.3-1.6" {...p} /></>,
    E: <><path d="m7.5 16.5 9-9" {...p} /><circle cx="8.5" cy="8.5" r="2" {...p} /><circle cx="15.5" cy="15.5" r="2" {...p} /></>,
    F: <><path d="M7 3.5h10v17l-2.5-1.6-2.5 1.6-2.5-1.6L7 20.5z" {...p} /><path d="M10 8h4M10 12h4" {...p} /></>,
    Z: <><path d="m4 15 5-5 3 3 8-8" {...p} /><path d="M16 5h4v4" {...p} /></>,
  };
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      {paths[k] || paths.A}
    </svg>
  );
}

/** 완료된 단계는 아이콘 자리에 체크 표시 */

export function rmDoneIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="m5 12.5 4.5 4.5L19 7"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
