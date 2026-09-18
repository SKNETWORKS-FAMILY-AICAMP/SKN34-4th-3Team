import React, { useState, useCallback } from 'react';
import { MenuDrawer } from './MenuDrawer.jsx';

export function Nav({ user, onLoginClick, onNavigate }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const close = useCallback(() => setMenuOpen(false), []);

  return (
    <React.Fragment>
      <header className="nav">
        <div className="wrap nav__row">
          <button className="brand" type="button" onClick={() => onNavigate('home')}>
            <span className="brand__mark" aria-hidden="true">ON</span>
            창업ON
          </button>
          <span className="nav__spacer" />
          {user && <span className="nav__user"><b>{user.name}</b>님</span>}
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
