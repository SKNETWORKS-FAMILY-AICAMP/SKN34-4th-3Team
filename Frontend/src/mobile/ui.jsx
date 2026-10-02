// 모바일 웹앱 공통 부품: 머리글, 세그먼트, 페이지 넘김, 바텀시트, 토스트, 채팅.
// 모든 화면은 한 화면 높이(100dvh) 안에 들어가야 하므로 목록은 남은 높이에 맞춰 개수를 정한다(usePageSize).
import React, { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { api } from '../api.js';
import { Markdown } from '../components/Markdown.jsx';

export const FEATURES = [
  { key: 'roadmap', no: '01', name: '창업 로드맵', short: '창업 로드맵', desc: '아이디어부터 스케일업까지' },
  { key: 'tax', no: '02', name: 'AI 세무 Assistant', short: 'AI 세무', desc: '세법 근거로 답하는 세무 상담' },
  { key: 'expenses', no: '03', name: '지출관리', short: '지출관리', desc: '영수증 판독과 경비 판정' },
  { key: 'bizplan', no: '04', name: '사업계획서', short: '사업계획서', desc: 'PSST 초안 작성과 평가' },
  { key: 'gov', no: '05', name: '공고지원 AI', short: '공고지원 AI', desc: '내 조건에 맞는 지원사업' },
  { key: 'mypage', no: '06', name: '마이페이지', short: '마이페이지', desc: '일정·저장·구독 관리' },
];
export const featureOf = (key) => FEATURES.find((f) => f.key === key);

/* ---------- 로고 · 아이콘 ---------- */
export function MLogo({ onClick }) {
  return (
    <button type="button" className="m-logo" onClick={onClick} aria-label="홈으로">
      <svg viewBox="0 0 64 64" aria-hidden="true">
        <circle cx="32" cy="32" r="30.65" fill="none" stroke="#2B6FEB" strokeWidth="3" />
        <path d="M39.87 23.73A11.6 11.6 0 1 0 39.87 40.27" fill="none" stroke="#2B6FEB" strokeWidth="5.6" strokeLinecap="round" />
        <circle cx="44.1" cy="32" r="4.2" fill="#22A06B" />
      </svg>
      <span>CHANGUP <b>ON</b></span>
    </button>
  );
}

export function Burger({ onClick }) {
  return (
    <button type="button" className="m-burger" onClick={onClick} aria-label="전체 메뉴 열기">
      <span /><span /><span />
    </button>
  );
}

export function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M5.5 11.5 12 5l6.5 6.5" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
  );
}

/* ---------- 기능 화면 머리글 (‹ 홈 · 번호+이름 · 햄버거) ---------- */
export function FeatureHeader({ feature, onHome, onMenu, backLabel = '홈', onBack }) {
  return (
    <header className="m-fhead">
      <button type="button" className="m-fhead__back" onClick={onBack || onHome}>‹ {backLabel}</button>
      <h1 className="m-fhead__title"><span className="m-no">{feature.no}</span>{feature.name}</h1>
      <Burger onClick={onMenu} />
    </header>
  );
}

/* ---------- 세그먼트 ---------- */
export function Seg({ items, value, onChange, className = '' }) {
  return (
    <div className={'m-seg ' + className} role="tablist">
      {items.map((it) => (
        <button key={it.key} type="button" role="tab" aria-selected={value === it.key}
          className={'m-seg__btn' + (value === it.key ? ' is-on' : '')} onClick={() => onChange(it.key)}>
          {it.label}
          {it.count != null && <span className="m-seg__n">{it.count}</span>}
        </button>
      ))}
    </div>
  );
}

/* ---------- 페이지 넘김 ‹ 1 / 2 › ---------- */
export function Pager({ page, pages, onChange }) {
  if (pages <= 1) return <div className="m-pager m-pager--empty" />;
  return (
    <div className="m-pager">
      <button type="button" onClick={() => onChange(Math.max(0, page - 1))} disabled={page === 0} aria-label="이전 페이지">‹</button>
      <span className="m-pager__n">{page + 1} / {pages}</span>
      <button type="button" onClick={() => onChange(Math.min(pages - 1, page + 1))} disabled={page >= pages - 1} aria-label="다음 페이지">›</button>
    </div>
  );
}

// 목록 영역의 실제 높이에 들어가는 행 수. 화면이 작아도 스크롤 없이 페이지 넘김으로 처리한다.
export function usePageSize(rowHeight, gap = 8, max = 99) {
  const ref = useRef(null);
  const [size, setSize] = useState(3);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const measure = () => {
      const h = el.clientHeight;
      if (h > 0) setSize(Math.max(1, Math.min(max, Math.floor((h + gap) / (rowHeight + gap)))));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [rowHeight, gap, max]);
  return [ref, size];
}

export function paginate(list, page, size) {
  const pages = Math.max(1, Math.ceil(list.length / size));
  const p = Math.min(page, pages - 1);
  return { pages, page: p, items: list.slice(p * size, p * size + size) };
}

/* ---------- 바텀시트 ---------- */
export function Sheet({ open, onClose, title, children, className = '' }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="m-sheet" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={'m-sheet__panel ' + className} role="dialog" aria-modal="true" aria-label={title}>
        <span className="m-sheet__handle" aria-hidden="true" />
        {title && <h2 className="m-sheet__title">{title}</h2>}
        <div className="m-sheet__body">{children}</div>
      </div>
    </div>
  );
}

/* ---------- 토스트 ---------- */
const ToastCtx = createContext(() => {});
export const useToast = () => useContext(ToastCtx);
export function ToastProvider({ children }) {
  const [msg, setMsg] = useState('');
  const timer = useRef(null);
  const show = useCallback((text) => {
    setMsg(text);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setMsg(''), 1800);
  }, []);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {msg && <div className="m-toast" role="status">{msg}</div>}
    </ToastCtx.Provider>
  );
}

/* ---------- 채팅 ---------- */
// 기존 AiConsult와 같은 API(chatRooms·chatHistory·chatStream)를 쓴다. 가장 최근 대화방을 이어서 쓴다.
export function useChat(category, userId) {
  const [rows, setRows] = useState([]); // { id, question, answer, pending }
  const [roomId, setRoomId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setRows([]);
    setRoomId(null);
    setReady(false);
    if (!userId) {
      setReady(true);
      return undefined;
    }
    let alive = true;
    Promise.all([api.chatRooms(category).catch(() => null), api.chatHistory(category).catch(() => null)])
      .then(([rooms, hist]) => {
        if (!alive) return;
        const room = rooms && rooms.rooms && rooms.rooms[0] ? rooms.rooms[0].id : null;
        const msgs = ((hist && hist.messages) || [])
          .filter((m) => room == null || m.room_id === room)
          .map((m) => ({ id: m.id, question: m.question, answer: m.answer }));
        setRoomId(room);
        setRows(msgs);
      })
      .finally(() => alive && setReady(true));
    return () => { alive = false; };
  }, [category, userId]);

  // extra: 화면별로 함께 보낼 값(예: 로드맵 코치의 roadmapStep)
  const send = useCallback(async (question, extra) => {
    const q = String(question || '').trim();
    if (!q || busy) return false;
    setBusy(true);
    const tempId = 'p' + Date.now();
    setRows((cur) => [...cur, { id: tempId, question: q, answer: '', pending: true }]);
    const patch = (fields) => setRows((cur) => cur.map((r) => (r.id === tempId ? { ...r, ...fields } : r)));
    try {
      const body = { question: q, category, ...(extra || {}) };
      if (roomId != null) body.roomId = roomId;
      const rag = await api.chatStream(body, { onDraft: (answer) => patch({ answer }) });
      patch({ answer: (rag && rag.answer) || '답변을 받지 못했어요.', pending: false, id: (rag && rag.messageId) || tempId });
      if (rag && rag.roomId != null) setRoomId(rag.roomId);
    } catch (e) {
      patch({
        answer: e && e.status === 401 ? '로그인이 필요해요.' : '답변을 받지 못했어요. 잠시 후 다시 시도해 주세요.',
        pending: false,
      });
    } finally {
      setBusy(false);
    }
    return true;
  }, [busy, category, roomId]);

  return { rows, busy, ready, send };
}

// 최근 메시지만 보여주고 위쪽은 페이드로 가린다(스크롤 없음).
export function ChatBubbles({ rows, max = 4, empty }) {
  const msgs = [];
  rows.forEach((r) => {
    msgs.push({ key: r.id + 'q', me: true, text: r.question });
    msgs.push({ key: r.id + 'a', me: false, text: r.answer, pending: r.pending && !r.answer });
  });
  const shown = msgs.slice(-max);
  return (
    <div className="m-chat">
      {shown.length === 0 && empty && <div className="m-chat__empty">{empty}</div>}
      <div className="m-chat__stack">
        {shown.map((m) => (
          <div key={m.key} className={'m-bubble ' + (m.me ? 'm-bubble--me' : 'm-bubble--ai')}>
            {m.pending ? (
              <span className="m-typing" aria-label="답변 작성 중"><i /><i /><i /></span>
            ) : m.me ? m.text : <Markdown text={m.text || ''} />}
          </div>
        ))}
      </div>
    </div>
  );
}

export function ChatInput({ onSend, busy, placeholder = '메시지를 입력하세요' }) {
  const [text, setText] = useState('');
  const submit = (e) => {
    e.preventDefault();
    if (!text.trim() || busy) return;
    onSend(text.trim());
    setText('');
  };
  return (
    <form className="m-chatin" onSubmit={submit}>
      <input value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} aria-label="메시지" />
      <button type="submit" className={'m-send' + (text.trim() ? ' is-on' : '')} disabled={!text.trim() || busy} aria-label="전송">
        <SendIcon />
      </button>
    </form>
  );
}

export function LoginNeeded({ onLogin, text = '로그인하면 이용할 수 있어요.' }) {
  return (
    <div className="m-glass m-login">
      <p>{text}</p>
      <button type="button" className="m-btn m-btn--primary" onClick={onLogin}>로그인</button>
    </div>
  );
}
