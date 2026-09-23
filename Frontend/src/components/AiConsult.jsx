import React, { useState, useEffect, useRef } from 'react';
import { api } from '../api.js';
import { AI_RULES, AI_SUGGESTIONS, AI_ERR } from '../constants.js';
import { dayKeyOf, dayLabel, rowsToTurns, linkBtn } from '../utils.js';
import { Markdown } from './Markdown.jsx';

const getConfirmationNotice = ({ status, guardrailReason } = {}) => {
  if (guardrailReason === 'out_of_scope') {
    return '답변할 수 없는 요청이에요. 창업·세금·지원사업과 관련된 질문으로 바꿔 주세요.';
  }
  if (guardrailReason === 'generation_validation_failed') {
    return '안전하게 확인되지 않은 답변이라 제공하지 않았어요. 질문을 구체적으로 바꿔 다시 시도해 주세요.';
  }
  if (status === 'integration_unavailable' || status === 'error') {
    return '지금은 답변을 확인할 수 없어요. 잠시 후 다시 시도해 주세요.';
  }
  return '추가 정보가 필요해요. 조건을 더 알려주시면 정확히 확인할 수 있어요.';
};

// 응답 대기·화면 전환에서 방을 구분하는 키. 서버 저장 전인 새 대화는 id가 없어 따로 표시한다.
const NEW_ROOM = 'new';
const roomKey = (id) => (id == null ? NEW_ROOM : id);

export function AiConsult({
  user,
  rules,
  title,
  suggestions,
  category,
  roadmapStep,
  allowSampleFallback = true,
  large,
  compact,
  noHeader,
  onRequireLogin,
  withSidebar,
}) {
  const RULES = rules || AI_RULES;
  const CHIPS = suggestions || AI_SUGGESTIONS;
  const userId = user && user.id;
  // category가 지정되고 로그인 상태일 때만 DB 기록을 불러온다. 세무·공고지원·로드맵이
  // 각각 다른 category를 넘겨 서로 다른 화면의 대화가 섞이지 않는다.
  const [sampleFn, setSampleFn] = useState(undefined); // undefined=연결중, null=불가, fn=사용가능
  const [turns, setTurns] = useState([]);
  const [draft, setDraft] = useState('');
  const [stream, setStream] = useState('');
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('');
  const [err, setErr] = useState('');
  const [histBusy, setHistBusy] = useState(false); // 기록 조회·삭제 진행 중
  const [histLoaded, setHistLoaded] = useState(false); // DB 기록 조회가 끝났는지(빈 기록 포함)
  const [rows, setRows] = useState([]); // 서버 기록 원본 (id·room_id 포함)
  const [roomList, setRoomList] = useState([]); // 서버 대화방 목록 (최근 대화 순)
  const [roomId, setRoomId] = useState(null); // 지금 보고 있는 방 (null=아직 저장 전인 새 대화)
  const [pendingKey, setPendingKey] = useState(null); // 응답을 기다리는 방의 roomKey (null=없음)
  const [renamingId, setRenamingId] = useState(null); // 지금 이름을 고치는 중인 방 id
  const [renameDraft, setRenameDraft] = useState('');
  const [needsLogin, setNeedsLogin] = useState(false);
  const bodyRef = useRef(null);
  const ctlRef = useRef(null);
  // 응답이 도착했을 때 "지금 보고 있는 방"이 바뀌어 있을 수 있어 최신 값을 ref로도 들고 있는다.
  const roomKeyRef = useRef(roomKey(roomId));
  useEffect(() => {
    roomKeyRef.current = roomKey(roomId);
  }, [roomId]);
  // 응답을 기다리는 방을 벗어났다 되돌아왔을 때 다시 보여줄 "질문까지는 던진" 상태 스냅샷
  const pendingTurnsRef = useRef(null);

  const turnsOf = (id, source = rows) => rowsToTurns(source.filter((r) => r.room_id === id));

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const s = window.claude && (await window.claude.use('sample'));
        if (alive) setSampleFn(() => s || null);
      } catch (e) {
        if (alive) setSampleFn(() => null);
      }
    })();
    return () => {
      alive = false;
      if (ctlRef.current) ctlRef.current.abort();
    };
  }, []);

  // 로그인 + category 지정 시 대화방 목록과 이전 질문·답변을 불러와 가장 최근 방을 연다.
  useEffect(() => {
    if (!userId || !category) {
      setHistLoaded(false);
      setTurns([]);
      setRows([]);
      setRoomList([]);
      setRoomId(null);
      return;
    }
    let alive = true;
    setHistBusy(true);
    setErr('');
    setTurns([]);
    Promise.all([api.chatRooms(category), api.chatHistory(category)])
      .then(([r, h]) => {
        if (!alive) return;
        const list = (r && r.rooms) || [];
        const fetched = (h && h.messages) || [];
        setRoomList(list);
        setRows(fetched);
        const first = list.length ? list[0].id : null;
        setRoomId(first);
        setTurns(first == null ? [] : turnsOf(first, fetched));
        setHistLoaded(true);
      })
      .catch(() => {
        if (!alive) return;
        setErr('이전 대화 기록을 불러오지 못했어요.');
        setHistLoaded(true);
      })
      .finally(() => {
        if (alive) setHistBusy(false);
      });
    return () => {
      alive = false;
    };
  }, [userId, category]);

  const clearHistory = async () => {
    if (histBusy || busy) return;
    if (!window.confirm('대화 기록을 모두 지울까요? 되돌릴 수 없어요.')) return;
    setHistBusy(true);
    setErr('');
    try {
      await api.clearChat(category);
      setTurns([]);
      setStream('');
      setRows([]);
      setRoomList([]);
      setRoomId(null);
    } catch (e) {
      setErr('대화 기록을 지우지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setHistBusy(false);
    }
  };

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [turns, stream, busy, progress]);


  const ask = async (text) => {
    const q = (text || '').trim();
    if (!q || busy) return;
    setErr('');
    setNeedsLogin(false);
    // 지금 보고 있는 방에 이어 쓴다. 새 대화면 첫 답변과 함께 서버가 방을 만든다.
    // 응답을 기다리는 동안에도 다른 방을 둘러볼 수 있다 — 이 방(askedKey)을 계속 보고 있을 때만
    // 도착하는 답변을 화면에 반영한다. 다른 방으로 옮겨갔다면 rows에만 쌓아 두고,
    // 나중에 이 방을 다시 열면(openRoom) rows로부터 다시 그려진다.
    const askedRoomId = roomId;
    let askedKey = roomKey(askedRoomId);
    const isViewingAsked = () => roomKeyRef.current === askedKey;
    const appendTurn = (entry) => {
      if (isViewingAsked()) setTurns((cur) => [...cur, entry]);
    };
    setPendingKey(askedKey);
    const nextTurns = [...turns, { role: 'user', content: q }];
    pendingTurnsRef.current = nextTurns;
    setTurns(nextTurns);
    setDraft('');
    setBusy(true);
    setStream('');
    setProgress('질문을 확인하고 있어요…');
    let elapsed = 0;
    const progressTimer = setInterval(() => {
      elapsed += 5;
      if (elapsed === 5) {
        setProgress(category === 'tax' ? '관련 세금 자료를 확인하고 있어요…' : '관련 정책 자료를 확인하고 있어요…');
      } else if (elapsed === 10) {
        setProgress('답변에 필요한 근거를 살펴보고 있어요…');
      } else {
        setProgress(`근거를 확인하고 있어요… (${elapsed}초 경과)`);
      }
    }, 5000);
    const ctl = new AbortController();
    ctlRef.current = ctl;

    // 1) Backend RAG — DB(세법 4,459조문 / 정책)에서 근거 문서 검색
    let rag = null;
    let needLogin = false;
    try {
      const chatBody = { question: q, category: category || 'tax' };
      if (category === 'roadmap' && roadmapStep) chatBody.roadmapStep = roadmapStep;
      if (askedRoomId != null) chatBody.roomId = askedRoomId;
      rag = await api.chat(chatBody, { signal: ctl.signal });
    } catch (e) {
      // 401은 "Backend가 안 떴다"가 아니라 "로그인이 필요하다"이다. 구분해서 안내한다.
      needLogin = e && e.status === 401;
    }
    // ChatMessageResponse에는 sources가 없다. messageId로 근거를 따로 받아온다.
    let sources = [];
    if (rag && rag.messageId) {
      try {
        const s = await api.chatSources(rag.messageId, { signal: ctl.signal });
        sources = (s && s.sources) || [];
      } catch (e) {
        /* 근거를 못 받아도 답변은 그대로 보여준다 */
      }
    }
    // 서버에 저장된 메시지와 방을 목록에도 반영한다.
    if (rag && rag.messageId != null && rag.roomId != null) {
      const now = new Date().toISOString();
      // created_at 을 빼면 사이드바에서 날짜를 못 읽어 '날짜 미상'으로 빠진다.
      setRows((cur) => [
        ...cur,
        { id: rag.messageId, room_id: rag.roomId, question: q, answer: rag.answer || '', created_at: now },
      ]);
      setRoomList((cur) => {
        const found = cur.find((r) => r.id === rag.roomId);
        const room = found
          ? { ...found, updatedAt: now }
          : { id: rag.roomId, category, title: null, firstQuestion: q, createdAt: now, updatedAt: now };
        return [room, ...cur.filter((r) => r.id !== rag.roomId)];
      });
      if (askedRoomId == null) {
        // 새 대화가 방금 서버 방이 됐다. 계속 보고 있었다면 그 방으로 전환한다.
        if (isViewingAsked()) {
          roomKeyRef.current = roomKey(rag.roomId);
          setRoomId(rag.roomId);
        }
        askedKey = roomKey(rag.roomId);
      }
    }

    // status가 error·integration_unavailable이면 LLM이 답하긴 했지만 근거를 만들지 못한 경우다.
    // 이때는 답변 문장 대신 아래 보조 경로로 내려간다. llmUsed는 호출 성공 여부만 뜻한다.
    const ragUsable =
      rag && rag.llmUsed && rag.status !== 'error' && rag.status !== 'integration_unavailable';
    try {
      if (ragUsable) {
        // 2) 설계 경로 — LLM 서비스(OpenAI)가 근거를 읽고 만든 답변을 그대로 쓴다.
        appendTurn({
          role: 'assistant',
          content: rag.answer,
          sources,
          needsConfirmation: rag.needsConfirmation,
          status: rag.status,
          guardrailReason: rag.guardrailReason,
        });
      } else if (sampleFn && allowSampleFallback) {
        // 3) Backend가 실답변을 못 준 경우에만 뷰어의 Claude로 생성한다(claude.ai 데모 보조).
        const ctx = sources.length
          ? '\n\n[DB에서 검색한 근거 문서 — 이 내용을 우선 활용하고 인용한 조문명을 답변에 표기해]\n' +
            sources
              .map((s, i) => `[${i + 1}] ${s.title}\n${(s.excerpt || '').slice(0, 500)}`)
              .join('\n\n')
          : '';
        const res = await sampleFn(
          [{ role: 'user', content: RULES + ctx }, ...nextTurns],
          {
            cache: false,
            modelTier: 'quick',
            signal: ctl.signal,
            onText: ({ text: t }) => {
              if (isViewingAsked()) setStream(t);
            },
          }
        );
        appendTurn({ role: 'assistant', content: res.text, sources });
      } else if (rag) {
        // 4) 둘 다 안 되면 Backend의 목업 안내라도 보여준다.
        appendTurn({
          role: 'assistant',
          content: rag.answer,
          sources,
          needsConfirmation: rag.needsConfirmation,
          status: rag.status,
          guardrailReason: rag.guardrailReason,
        });
      } else if (needLogin) {
        if (isViewingAsked()) {
          setNeedsLogin(true);
          setErr('로그인이 필요한 기능이에요. 로그인하면 내 사업자 정보에 맞춰 답해 드려요.');
        }
      } else if (isViewingAsked()) {
        setErr(
          '지금은 답변을 불러올 수 없어요. 잠시 후 다시 시도해 주세요.'
        );
      }
    } catch (e) {
      const code = e && e.code;
      if (code === 'cancelled') {
        if (e.text) appendTurn({ role: 'assistant', content: e.text + ' …(중단됨)' });
      } else if (rag) {
        appendTurn({
          role: 'assistant',
          content: rag.answer,
          sources,
          needsConfirmation: rag.needsConfirmation,
          status: rag.status,
          guardrailReason: rag.guardrailReason,
        });
      } else {
        if (isViewingAsked()) setErr(AI_ERR[code] || '응답을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.');
        if (e && e.text) {
          appendTurn({ role: 'assistant', content: e.text + ' …(오류로 중단됨)' });
        }
      }
    } finally {
      clearInterval(progressTimer);
      setBusy(false);
      setStream('');
      setProgress('');
      setPendingKey(null);
      pendingTurnsRef.current = null;
      ctlRef.current = null;
    }
  };

  // 사이드바 목록: 직접 정한 이름이 없으면 첫 질문을 제목으로, 마지막 대화 시각을 날짜로 쓴다.
  // 아직 저장 전인 새 대화는 지금 보고 있거나 응답을 기다리는 중일 때만 맨 위에 둔다.
  const sideRooms = roomList.map((r) => ({
    id: r.id,
    title: r.title || r.firstQuestion || '새 대화',
    day: dayKeyOf(r.updatedAt),
  }));
  if (roomId == null || pendingKey === NEW_ROOM) {
    sideRooms.unshift({
      id: null,
      // 서버 확인 전(응답 대기 중)이라 목록엔 아직 없다 — 방금 던진 질문을 스냅샷에서 보여준다.
      title: pendingKey === NEW_ROOM && pendingTurnsRef.current && pendingTurnsRef.current[0]
        ? pendingTurnsRef.current[0].content
        : '새 대화',
      day: dayKeyOf(new Date()),
    });
  }

  // 같은 날짜끼리 한 묶음으로 모은다. 최신 날짜부터, 날짜를 모르는 옛 기록은 맨 아래로 내린다.
  const roomGroups = [];
  const byDay = new Map();
  sideRooms.forEach((room) => {
    let grp = byDay.get(room.day);
    if (!grp) {
      grp = { day: room.day, rooms: [] };
      byDay.set(room.day, grp);
      roomGroups.push(grp);
    }
    grp.rooms.push(room);
  });
  roomGroups.sort((a, b) => (b.day || '').localeCompare(a.day || ''));

  const openRoom = (id) => {
    // 응답을 기다리는 동안에도 다른 방을 볼 수 있다 — 지금 응답 중인 방만 클릭으로 막을 이유가 없다.
    if (histBusy || id === roomId) return;
    roomKeyRef.current = roomKey(id);
    setRoomId(id);
    if (roomKey(id) === pendingKey && pendingTurnsRef.current) {
      // 아직 답이 안 온 방으로 돌아온 것 — 서버 기록(rows)엔 없으니 던져둔 질문 그대로 복원한다.
      setTurns(pendingTurnsRef.current);
    } else {
      setTurns(turnsOf(id));
      setStream('');
    }
    setErr('');
  };

  // 대화방 이름 바꾸기 — 서버에 저장해 다른 기기에서도 같은 이름으로 보인다.
  const startRename = (id, current) => {
    setRenamingId(id);
    setRenameDraft(current);
  };
  const cancelRename = () => {
    setRenamingId(null);
    setRenameDraft('');
  };
  const submitRename = async (id) => {
    const name = renameDraft.trim() || null; // 비워서 저장하면 기본 제목(첫 질문)으로 되돌아간다
    setRenamingId(null);
    setRenameDraft('');
    try {
      await api.renameChatRoom(id, name);
      setRoomList((cur) => cur.map((r) => (r.id === id ? { ...r, title: name } : r)));
    } catch (e) {
      setErr('대화방 이름을 바꾸지 못했어요. 잠시 후 다시 시도해 주세요.');
    }
  };

  const deleteRoom = async (room) => {
    if (busy || histBusy || roomKey(room.id) === pendingKey) return; // 응답 기다리는 방은 지울 수 없다
    if (!window.confirm('이 대화방을 삭제할까요?\n되돌릴 수 없습니다.')) return;

    if (room.id == null) {
      // 아직 메시지가 없는 "새 대화" — 지울 서버 기록이 없으니 가장 최근 방으로 되돌린다.
      const first = roomList.length ? roomList[0].id : null;
      roomKeyRef.current = roomKey(first);
      setRoomId(first);
      setTurns(first == null ? [] : turnsOf(first));
      setStream('');
      setErr('');
      return;
    }

    try {
      await api.deleteChatRoom(room.id);
    } catch (e) {
      setErr('대화방을 지우지 못했어요. 잠시 후 다시 시도해 주세요.');
      return;
    }
    setRoomList((cur) => cur.filter((r) => r.id !== room.id));
    setRows((cur) => cur.filter((r) => r.room_id !== room.id));
    if (room.id === roomId) {
      roomKeyRef.current = NEW_ROOM;
      setRoomId(null);
      setTurns([]);
      setStream('');
    }
    setErr('');
  };

  // 지금 대화는 그대로 두고 빈 방을 새로 연다. 방은 첫 질문을 보낼 때 서버에 만들어진다.
  const startNew = () => {
    if (busy || histBusy) return;
    setErr('');
    setStream('');
    if (roomId == null && turns.length === 0) return; // 이미 비어 있는 새 대화
    roomKeyRef.current = NEW_ROOM;
    setRoomId(null);
    setTurns([]);
  };

  const panel = (
    <div className={'ai' + (large ? ' ai--lg' : '') + (compact ? ' ai--compact' : '')}>
      {!noHeader && (
        <div className="ai__bar">
          <span className="chatbox__ava" aria-hidden="true">ON</span>
          <span className="chatbox__who">
            <b>{title || 'AI 세무·창업 상담'}</b>
          </span>
        </div>
      )}

      {category && userId && histLoaded && turns.length > 0 && (
        <div className="ai__histrow">
          <button
            type="button"
            style={{ ...linkBtn, opacity: histBusy || busy ? 0.5 : 1 }}
            disabled={histBusy || busy}
            onClick={clearHistory}
          >
            대화 기록 지우기
          </button>
        </div>
      )}

      <div className="ai__body" ref={bodyRef}>
        {histBusy && turns.length === 0 && (
          <div className="ai__hint">이전 대화를 불러오는 중…</div>
        )}
        {!histBusy && turns.length === 0 && pendingKey !== roomKey(roomId) && (
          <div className="ai__hint">
            <b className="ai__hintttl">어떤 게 궁금하신가요?</b>
            <span className="ai__hintsub">{user.biz} · {user.region} 기준으로 답해 드려요. 아래를 눌러 시작해 보세요.</span>
            <div className="ai__chips">
              {CHIPS.map((s) => (
                <button key={s} type="button" className="ai__chip" disabled={busy}
                  onClick={() => ask(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((m, i) => (
          <React.Fragment key={i}>
            <div className={`msg msg-in msg--${m.role === 'assistant' ? 'ai' : 'user'}`}>
              {m.role === 'assistant' ? <Markdown text={m.content} /> : m.content}
            </div>
            {m.needsConfirmation && (
              <div className="msg-src">
                <b>{getConfirmationNotice(m)}</b>
              </div>
            )}
            {m.sources && m.sources.length > 0 && (
              <div className="msg-src">
                <b>확인한 자료 {m.sources.length}건</b>
                {m.sources.map((s, si) => (
                  <a key={si} href={s.url || '#'} target="_blank" rel="noreferrer">
                    [{si + 1}] {s.lawName ? `${s.lawName} · ` : ''}{s.title}
                  </a>
                ))}
              </div>
            )}
          </React.Fragment>
        ))}
        {pendingKey === roomKey(roomId) &&
          (stream ? (
            <div className="msg msg--ai"><Markdown text={stream} /></div>
          ) : (
            <div className="ai__progress" role="status" aria-live="polite">
              <span className="typing" aria-hidden="true"><i /><i /><i /></span>
              <span>{progress}</span>
            </div>
          ))}
      </div>

      {err && (
        <p className="ai__err">
          {err}
          {needsLogin && onRequireLogin && (
            <button type="button" onClick={onRequireLogin}
              style={{
                marginLeft: 8, padding: '3px 10px', border: 0, borderRadius: 8,
                background: 'var(--blue)', color: '#fff', fontSize: 12, fontWeight: 700,
                cursor: 'pointer',
              }}>로그인</button>
          )}
        </p>
      )}

      <form className="ai__foot" onSubmit={(e) => { e.preventDefault(); ask(draft); }}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={
            busy && pendingKey !== roomKey(roomId)
              ? '다른 대화방에서 응답을 기다리는 중이에요…'
              : '메시지를 입력하세요'
          }
          aria-label="메시지 입력"
          disabled={busy}
        />
        {busy ? (
          <button type="button" className="ai__send" onClick={() => ctlRef.current && ctlRef.current.abort()}>
            중지
          </button>
        ) : (
          <button type="submit" className="ai__send" disabled={!draft.trim()}>
            전송
          </button>
        )}
      </form>
    </div>
  );

  if (!withSidebar) return panel;

  return (
    <div className="cvx">
      <aside className="cvx__side">
        <button type="button" className="cvx__new" onClick={startNew} disabled={busy || histBusy}>
          + 새 대화 시작
        </button>
        <nav className="cvx__list" aria-label="대화 목록">
          {histBusy ? (
            <p className="cvx__empty">기록을 불러오는 중…</p>
          ) : (
            <React.Fragment>
              {roomGroups.map((grp) => (
                <React.Fragment key={grp.day || 'none'}>
                  <div className="cvx__group">
                    {dayLabel(grp.day)}
                    <span className="cvx__group-n">{grp.rooms.length}</span>
                  </div>
                  {grp.rooms.map((room) =>
                    room.id != null && renamingId === room.id ? (
                      <form
                        key={room.id}
                        className="cvx__rename"
                        onSubmit={(e) => {
                          e.preventDefault();
                          submitRename(room.id);
                        }}
                      >
                        <input
                          autoFocus
                          value={renameDraft}
                          onChange={(e) => setRenameDraft(e.target.value)}
                          onBlur={() => submitRename(room.id)}
                          onKeyDown={(e) => {
                            if (e.key === 'Escape') cancelRename();
                          }}
                          aria-label="대화방 이름"
                          placeholder="대화방 이름"
                        />
                        <button type="submit" aria-label="이름 저장">✓</button>
                      </form>
                    ) : (
                      <div key={roomKey(room.id)} className={'cvx__row' + (room.id === roomId ? ' is-active' : '')}>
                        <button
                          type="button"
                          className="cvx__conv"
                          aria-current={room.id === roomId ? 'true' : undefined}
                          onClick={() => openRoom(room.id)}
                        >
                          {room.title}
                          {roomKey(room.id) === pendingKey && (
                            <span className="cvx__pending" title="응답을 기다리는 중이에요" aria-label="응답 대기 중">
                              <i /><i /><i />
                            </span>
                          )}
                        </button>
                        {room.id != null && (
                          <button
                            type="button"
                            className="cvx__edit"
                            aria-label="대화방 이름 바꾸기"
                            onClick={(e) => {
                              e.stopPropagation();
                              startRename(room.id, room.title);
                            }}
                          >
                            ✎
                          </button>
                        )}
                        {roomKey(room.id) !== pendingKey && (
                          <button
                            type="button"
                            className="cvx__edit cvx__del"
                            aria-label="대화방 삭제"
                            onClick={(e) => {
                              e.stopPropagation();
                              deleteRoom(room);
                            }}
                          >
                            🗑
                          </button>
                        )}
                      </div>
                    )
                  )}
                </React.Fragment>
              ))}
            </React.Fragment>
          )}
        </nav>
      </aside>
      <div className="cvx__main">{panel}</div>
    </div>
  );
}

/* ---------- 마이페이지 ---------- */
/* ===== 마이페이지: 일정 캘린더 (확인 + 추가/삭제) ===== */
