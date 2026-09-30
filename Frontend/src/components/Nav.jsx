import React, { useState, useCallback } from 'react';
import { LogoMark, BrandWord } from './LogoMark.jsx';
import { MenuDrawer } from './MenuDrawer.jsx';

export function Nav({ user, onLoginClick, onNavigate }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const close = useCallback(() => setMenuOpen(false), []);

  return (
    <React.Fragment>
      {/* 서브 페이지 머리글(.rmhead)과 같은 폭·높이·배치. .nav는 상단 고정과 설치 앱 창 드래그 영역만 맡는다. */}
      <header className="nav rmhead">
        <div className="rmhead__in">
          <button className="brand" type="button" onClick={() => onNavigate('home')}>
            <LogoMark />
            <BrandWord />
          </button>
          <button className="hamburger" type="button"
            aria-haspopup="dialog" aria-expanded={menuOpen}
            aria-label="메뉴 열기" onClick={() => setMenuOpen(true)}>
            <span /><span /><span />
          </button>
        </div>
      </header>
      <MenuDrawer open={menuOpen} onClose={close} onNavigate={onNavigate}
        user={user} onAuth={onLoginClick} />
    </React.Fragment>
  );
}

/* ---------- 서브 페이지 ---------- */
/* ===== 정부지원사업 탐색 ===== */
