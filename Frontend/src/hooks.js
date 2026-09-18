import { useState, useEffect, useRef, useCallback } from 'react';

export const prefersReducedMotion =
  typeof window !== 'undefined' && window.matchMedia &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ---------- 공용 훅 ---------- */

export function useInView(opts, repeat) {
  const ref = useRef(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') {
      setInView(true);
      return;
    }
    const el = ref.current;
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            setInView(true);
            if (!repeat) io.disconnect();
          } else if (repeat) {
            setInView(false);
          }
        });
      },
      opts || { threshold: 0.16, rootMargin: '0px 0px -10% 0px' }
    );
    if (el) io.observe(el);
    const failsafe = repeat ? null : setTimeout(() => setInView(true), 2800);
    return () => {
      io.disconnect();
      if (failsafe) clearTimeout(failsafe);
    };
  }, [repeat]);
  return [ref, inView];
}

export function useCountUp(target, run, duration = 1200) {
  const [value, setValue] = useState(prefersReducedMotion ? target : 0);
  useEffect(() => {
    if (prefersReducedMotion) {
      setValue(target);
      return;
    }
    if (!run) {
      setValue(0);
      return;
    }
    let raf;
    const start = performance.now();
    const tick = (now) => {
      const p = Math.min(1, (now - start) / duration);
      setValue(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, run, duration]);
  return value;
}

export function useThemeToggle() {
  return useCallback(() => {
    const isDark =
      document.documentElement.getAttribute('data-theme') === 'dark' ||
      (!document.documentElement.getAttribute('data-theme') &&
        window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.setAttribute('data-theme', isDark ? 'light' : 'dark');
  }, []);
}

/* 어느 페이지에서나 보이는 고정 다크모드 토글 */
