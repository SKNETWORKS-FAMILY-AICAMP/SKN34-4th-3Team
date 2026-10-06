import React, { useEffect, useState } from 'react';
import { LogoMark, BrandWord } from './LogoMark.jsx';
import { createPortal } from 'react-dom';
import { api } from '../api.js';
import { NAV_MENU } from '../constants.js';
import { pad2 } from '../utils.js';
import { useThemeToggle } from '../hooks.js';

export function MenuDrawer({ open, onClose, onNavigate, user, onAuth }) {
  const toggleTheme = useThemeToggle();
  // 지금 화면에 사용 가이드(? 버튼)가 있는지. 메뉴를 열 때마다 확인한다.
  const [hasTour, setHasTour] = useState(false);
  useEffect(() => {
    if (open) setHasTour(!!document.querySelector('.tour-fab'));
  }, [open]);
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
            <LogoMark /><BrandWord />
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
        {/* 반응형 웹앱의 휴대폰 폭에서만 보인다(web.css). 떠 있는 ?/◐ 버튼을 메뉴 안으로 옮긴 것. */}
        <div className="drawer__tools">
          <button type="button" className="drawer__tool" onClick={toggleTheme}>
            <span aria-hidden="true">◐</span>다크 모드 전환
          </button>
          {hasTour && (
            <button type="button" className="drawer__tool"
              onClick={() => {
                onClose();
                // 숨겨 둔 ? 버튼을 대신 눌러 이 화면의 사용 가이드를 연다(메뉴가 닫힌 뒤).
                setTimeout(() => { const b = document.querySelector('.tour-fab'); if (b) b.click(); }, 250);
              }}>
              <span aria-hidden="true">?</span>이 화면 사용 가이드
            </button>
          )}
        </div>
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
