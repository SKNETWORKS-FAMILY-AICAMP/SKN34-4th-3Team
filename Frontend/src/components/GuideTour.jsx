import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';

// 화면 요소를 차례로 강조하며 설명하는 온보딩 투어.
// steps: [{ target: CSS 선택자 | null(가운데 카드), title, body }]
// 대상이 화면에 없는 단계는 건너뛴다(예: 다른 단계 화면에서 다시 볼 때).
const PAD = 8;
const GAP = 14;
const CARD_W = 340;
const MOBILE = 640;

// 화면에 실제로 보이는(숨김 처리되지 않은) 첫 요소를 찾는다.
function findTarget(step) {
  if (!step || !step.target) return null;
  return [...document.querySelectorAll(step.target)].find((el) => el.getClientRects().length > 0) || null;
}

function placeCard(rect, card, vw, vh) {
  if (!rect || vw <= MOBILE) return null;
  const w = card.width;
  const h = card.height;
  const clampX = (x) => Math.max(16, Math.min(x, vw - w - 16));
  const clampY = (y) => Math.max(16, Math.min(y, vh - h - 16));
  const top = Math.max(rect.top, 0);
  const bottom = Math.min(rect.bottom, vh);
  // 오른쪽 → 아래 → 위 → 왼쪽 순서로 들어갈 자리를 찾는다.
  if (rect.right + PAD + GAP + w + 16 <= vw) return { left: rect.right + PAD + GAP, top: clampY(top) };
  if (bottom + PAD + GAP + h + 16 <= vh) return { left: clampX(rect.left), top: bottom + PAD + GAP };
  if (top - PAD - GAP - h >= 16) return { left: clampX(rect.left), top: top - PAD - GAP - h };
  if (rect.left - PAD - GAP - w >= 16) return { left: rect.left - PAD - GAP - w, top: clampY(top) };
  // 대상이 화면을 거의 채우면 오른쪽 아래 구석에 띄운다.
  return { left: vw - w - 24, top: vh - h - 24 };
}

export function GuideTour({ open, steps, onClose, label = '사용 가이드' }) {
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState(null);
  const [pos, setPos] = useState(null);
  const [visible, setVisible] = useState([]);
  const cardRef = useRef(null);
  const step = visible[Math.min(index, visible.length - 1)];
  const last = index >= visible.length - 1;

  // 열 때 지금 화면에 있는 대상만 골라 단계 목록을 고정한다(도중에 목록이 바뀌어 번호가 흔들리지 않게).
  useEffect(() => {
    if (!open) return;
    setIndex(0);
    setVisible(steps.filter((s) => !s.target || findTarget(s)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const measure = useCallback(() => {
    const el = findTarget(step);
    if (!el) {
      setRect(null);
      return;
    }
    const r = el.getBoundingClientRect();
    setRect({ top: r.top, left: r.left, right: r.right, bottom: r.bottom, width: r.width, height: r.height });
  }, [step]);

  // 단계가 바뀌면 대상을 화면 안으로 스크롤하고, 스크롤·리사이즈 때마다 위치를 다시 잰다.
  useEffect(() => {
    if (!open || !step) return undefined;
    const el = findTarget(step);
    if (el) {
      const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      const r = el.getBoundingClientRect();
      // 모바일은 안내 카드가 화면 아래를 덮으므로 대상을 항상 위쪽으로 올린다.
      const mobile = window.innerWidth <= MOBILE;
      const fits = r.top >= 16 && r.bottom <= window.innerHeight - 16;
      if (mobile || !fits) {
        el.scrollIntoView({
          behavior: reduce ? 'auto' : 'smooth',
          block: mobile || r.height > window.innerHeight * 0.7 ? 'start' : 'center',
        });
      }
    }
    measure();
    // 부드러운 스크롤이 끝날 때까지 잠시 매 프레임 위치를 따라간다.
    let frame = 0;
    const until = performance.now() + 700;
    const follow = () => {
      measure();
      if (performance.now() < until) frame = requestAnimationFrame(follow);
    };
    frame = requestAnimationFrame(follow);
    window.addEventListener('scroll', measure, true);
    window.addEventListener('resize', measure);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('scroll', measure, true);
      window.removeEventListener('resize', measure);
    };
  }, [open, step, measure]);

  useLayoutEffect(() => {
    if (!open || !cardRef.current) return;
    const c = cardRef.current.getBoundingClientRect();
    setPos(placeCard(rect, { width: c.width, height: c.height }, window.innerWidth, window.innerHeight));
  }, [open, rect, index]);

  useEffect(() => {
    if (open && cardRef.current) cardRef.current.focus({ preventScroll: true });
  }, [open, index]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowRight') setIndex((i) => Math.min(i + 1, visible.length - 1));
      else if (e.key === 'ArrowLeft') setIndex((i) => Math.max(i - 1, 0));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose, visible.length]);

  if (!open || !step) return null;

  const spot = rect && {
    top: Math.max(rect.top - PAD, 4),
    left: rect.left - PAD,
    width: rect.width + PAD * 2,
    height: Math.min(rect.bottom + PAD, window.innerHeight - 4) - Math.max(rect.top - PAD, 4),
  };
  const titleId = 'guide-tour-title';

  return (
    <div className="gt" role="presentation">
      {spot ? <div className="gt__spot" style={spot} aria-hidden="true" /> : <div className="gt__dim" aria-hidden="true" />}
      <div
        ref={cardRef}
        className={'gt__card' + (rect ? '' : ' is-center') + (pos ? '' : ' is-sheet')}
        style={pos && rect ? { left: pos.left, top: pos.top, width: CARD_W } : undefined}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <div className="gt__top">
          <span className="gt__label">{label}</span>
          <span className="gt__count">{index + 1} / {visible.length}</span>
        </div>
        <h3 id={titleId} className="gt__title">{step.title}</h3>
        <div className="gt__body">{step.body}</div>
        <div className="gt__dots" aria-hidden="true">
          {visible.map((s, i) => <i key={i} className={i === index ? 'is-on' : i < index ? 'is-done' : ''} />)}
        </div>
        <div className="gt__actions">
          {!last && <button type="button" className="gt__skip" onClick={onClose}>건너뛰기</button>}
          <span className="gt__spacer" />
          {index > 0 && (
            <button type="button" className="gt__prev" onClick={() => setIndex(index - 1)}>이전</button>
          )}
          <button type="button" className="gt__next" onClick={() => (last ? onClose() : setIndex(index + 1))}>
            {last ? '시작하기' : '다음'}
          </button>
        </div>
      </div>
    </div>
  );
}
