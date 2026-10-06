// 전체 메뉴: 흰 전체 화면. 6개 기능 행 + 사용자 · 플랜 + 로그아웃.
import React, { useEffect, useState } from 'react';
import { api } from '../api.js';
import { FEATURES, MLogo } from './ui.jsx';

const PLAN_NAMES = { free: '무료 플랜', basic: '베이직 플랜', pro: '프로 플랜' };

export function MMenu({ user, current, go, onClose, onLogin, onLogout }) {
  const [plan, setPlan] = useState('');
  useEffect(() => {
    if (!user) return undefined;
    let alive = true;
    api.subscription()
      .then((s) => alive && setPlan(PLAN_NAMES[s && (s.plan || s.key)] || '무료 플랜'))
      .catch(() => alive && setPlan('무료 플랜'));
    return () => { alive = false; };
  }, [user]);

  return (
    <div className="m-menu" role="dialog" aria-modal="true" aria-label="전체 메뉴">
      <div className="m-menu__top">
        <MLogo onClick={() => go('home')} />
        <button type="button" className="m-menu__close" onClick={onClose} aria-label="메뉴 닫기">✕</button>
      </div>
      <nav className="m-menu__list">
        {FEATURES.map((f) => (
          <button key={f.key} type="button" className={'m-menu__row' + (current === f.key ? ' is-on' : '')}
            onClick={() => go(f.key)} aria-current={current === f.key ? 'page' : undefined}>
            <span className="m-no">{f.no}</span>
            <b className="m-menu__name">{f.short}</b>
            <span className="m-menu__desc">{f.desc}</span>
          </button>
        ))}
      </nav>
      <div className="m-menu__foot">
        {user ? (
          <>
            <span><b>{user.name}</b>님 · {plan || '무료 플랜'}</span>
            <button type="button" className="m-menu__logout" onClick={() => { onClose(); onLogout(); }}>로그아웃</button>
          </>
        ) : (
          <>
            <span>로그인하고 모든 기능을 이용해 보세요</span>
            <button type="button" className="m-menu__logout" onClick={() => { onClose(); onLogin(); }}>로그인</button>
          </>
        )}
      </div>
    </div>
  );
}
