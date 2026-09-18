import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { api } from '../api.js';
import { NAV_MENU, DEMO_EMAIL, DEMO_PASSWORD } from '../constants.js';
import { pad2 } from '../utils.js';

export function MenuDrawer({ open, onClose, onNavigate, user, onAuth }) {
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener('keydown', onKey);
    };
  }, [open, onClose]);

  const node = (
    <div className={'drawer-root' + (open ? ' is-open' : '')} aria-hidden={!open}>
      <div className="drawer-overlay" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="전체 메뉴">
        <div className="drawer__top">
          <span className="drawer__brand">
            <span className="brand__mark" aria-hidden="true">ON</span>창업ON
          </span>
          <button className="drawer__close" type="button" onClick={onClose} aria-label="메뉴 닫기">×</button>
        </div>
        <ul className="drawer__list">
          {NAV_MENU.map((m, i) => (
            <li className="drawer__item" key={m.key} style={{ '--i': i }}>
              <button
                className="drawer__link"
                type="button"
                onClick={() => {
                  onClose();
                  onNavigate(m.key);
                }}
              >
                <span className="drawer__num">{pad2(i + 1)}</span>
                <span>{m.label}</span>
                <span className="drawer__desc">{m.desc}</span>
              </button>
            </li>
          ))}
        </ul>
        <div className="drawer__foot">
          {user ? (
            <React.Fragment>
              <div className="drawer__auth">
                <span className="drawer__user">
                  <b>{user.name}</b><span>님</span>
                </span>
                <button className="btn btn--ghost" type="button"
                  onClick={() => { onClose(); onAuth(); }}>로그아웃</button>
              </div>
            </React.Fragment>
          ) : (
            <React.Fragment>
              <button className="btn btn--primary drawer__login" type="button"
                onClick={() => { onClose(); onAuth(); }}>로그인</button>
            </React.Fragment>
          )}
        </div>
      </aside>
    </div>
  );
  return createPortal(node, document.body);
}

/* ---------- 로그인 / 회원가입 모달 ---------- */
