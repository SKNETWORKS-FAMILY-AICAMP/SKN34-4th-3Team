import React, { useEffect, useRef } from 'react';
import { useInView, useCountUp, useThemeToggle, prefersReducedMotion } from '../hooks.js';

export function Reveal({ children, delay = 0, as: Tag = 'div', className = '' }) {
  const [ref, inView] = useInView(undefined, true);
  const shown = prefersReducedMotion || inView;
  return (
    <Tag
      ref={ref}
      className={`reveal ${shown ? 'is-in' : ''} ${className}`.trim()}
      style={{ '--d': `${delay}ms` }}
    >
      {children}
    </Tag>
  );
}

export function Metric({ value, suffix, label, delay }) {
  const [ref, inView] = useInView({ threshold: 0.5 }, true);
  const n = useCountUp(value, inView);
  return (
    <div className="reveal metric is-in" ref={ref} style={{ '--d': `${delay}ms` }}>
      <b className="u-num">
        {n.toLocaleString()}
        {suffix}
      </b>
      <span>{label}</span>
    </div>
  );
}

export function ScrollProgress() {
  const ref = useRef(null);
  useEffect(() => {
    let raf = 0;
    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const h = document.documentElement;
        const max = h.scrollHeight - h.clientHeight;
        const p = max > 0 ? h.scrollTop / max : 0;
        if (ref.current) ref.current.style.setProperty('--p', p.toFixed(4));
      });
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  return <div className="progress" ref={ref} aria-hidden="true" />;
}

export function FloatingThemeToggle() {
  const toggleTheme = useThemeToggle();
  return (
    <button
      className="theme-fab"
      type="button"
      onClick={toggleTheme}
      aria-label="밝은 테마와 어두운 테마 전환"
      title="다크 모드 전환"
    >
      ◐
    </button>
  );
}

/* ---------- 메뉴 드로어 ---------- */
