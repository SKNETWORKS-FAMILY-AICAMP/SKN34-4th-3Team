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
    // 설치 앱(PWA)의 상태바·타이틀바 색도 새 테마 배경(--ground)에 맞춘다.
    const color = isDark ? '#f4f6fd' : '#0d101e';
    document
      .querySelectorAll('meta[name="theme-color"]')
      .forEach((m) => m.setAttribute('content', color));
  }, []);
}

/* ---------- PWA 설치 ---------- */

// beforeinstallprompt 는 React 마운트 전에 올 수 있어 모듈 로드 시점부터 받아 둔다.
let deferredInstall = null;
if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredInstall = e;
  });
  window.addEventListener('appinstalled', () => {
    deferredInstall = null;
  });
}

const isStandalone = () =>
  typeof window !== 'undefined' &&
  ((window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) ||
    window.navigator.standalone === true);

const isIOS = () =>
  /iphone|ipad|ipod/i.test(navigator.userAgent) ||
  (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

export function useInstallPrompt() {
  const [installed] = useState(isStandalone);
  const install = useCallback(async () => {
    if (deferredInstall) {
      const e = deferredInstall;
      deferredInstall = null; // prompt() 는 이벤트당 1회만 호출 가능
      e.prompt();
      await e.userChoice;
      return;
    }
    // Safari·Firefox·인앱 브라우저 또는 이미 설치된 경우 이벤트가 오지 않는다.
    window.alert(
      isIOS()
        ? 'Safari 하단의 공유 버튼(□↑)을 누른 뒤 "홈 화면에 추가"를 선택해 주세요.'
        : '브라우저 메뉴에서 "앱 설치" 또는 "홈 화면에 추가"를 선택해 주세요.\n' +
            '이미 설치했다면 설치된 창업ON 앱에서 실행해 주세요.\n' +
            '카카오톡 등 앱 내 브라우저에서는 Chrome·Safari로 열어 주세요.'
    );
  }, []);
  return { installed, install };
}

/* 어느 페이지에서나 보이는 고정 다크모드 토글 */
