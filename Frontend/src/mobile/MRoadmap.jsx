// 01 창업 로드맵(대화형 코치): 고정 헤더 + 7단계 스트립 → 코치 대화(할 일 카드가 대화 속에 들어감) → 하단 입력.
// 체크는 App의 updateRoadmapDone(서버 저장), 대화는 PC 로드맵 AI 코치와 같은 category='roadmap' + roadmapStep을 쓴다.
// 이 화면은 대화가 길어지므로 앱 공통 3b 규칙(스크롤 금지) 대신 대화 영역만 세로 스크롤한다.
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ROADMAP, ROADMAP_TASKS, RM_GRADES } from '../constants.js';
import { Markdown } from '../components/Markdown.jsx';
import { MLogo, SendIcon, Sheet, useChat } from './ui.jsx';

const SUGGESTIONS = ['남은 작업 알려줘', '지원사업 서류 뭐가 필요해?', '다음 단계는 언제 시작해?'];

const tasksOf = (k) => ROADMAP_TASKS[k] || [];
const doneCount = (k, done) => tasksOf(k).filter((_, i) => done[`${k}:${i}`]).length;

function TaskCard({ stage, done, onToggle, onBasis, onAsk }) {
  const tasks = tasksOf(stage.k);
  const n = doneCount(stage.k, done);
  return (
    <section className="m-rm-card" aria-label={`${stage.t} 할 일`}>
      <header className="m-rm-card__head">
        <div>
          <span className="m-rm-card__kicker">{stage.phase} · 이 단계 할 일</span>
          <b className="m-rm-card__goal">{stage.t}</b>
          <p className="m-rm-card__desc">{stage.d}</p>
        </div>
        <span className={'m-rm-card__n' + (n === tasks.length ? ' is-done' : '')}>{n}/{tasks.length}</span>
      </header>
      <ul className="m-rm-card__list">
        {tasks.map((t, i) => {
          const key = `${stage.k}:${i}`;
          const on = !!done[key];
          return (
            <li key={key} className={on ? 'is-done' : ''}>
              <button type="button" className="m-rm-chk" role="checkbox" aria-checked={on} onClick={() => onToggle(key)}>
                <span aria-hidden="true" />
              </button>
              <span className="m-rm-card__t">{t.t}</span>
              <span className="m-rm-card__badges">
                <button type="button" className={'m-rm-badge is-' + ((RM_GRADES[t.grade] || {}).cls || 'ref')}
                  onClick={() => onBasis(t)} aria-label={`${t.grade} 근거 보기`}>{t.grade}</button>
                {t.key && <span className="m-rm-badge is-key">놓치면 손해</span>}
              </span>
            </li>
          );
        })}
      </ul>
      <button type="button" className="m-rm-card__ask" onClick={() => onAsk(stage)} disabled={n === tasks.length}>
        {n === tasks.length ? '이 단계 할 일을 모두 마쳤어요' : '남은 작업 진행 방법 물어보기 →'}
      </button>
    </section>
  );
}

export function MRoadmap({ user, roadmapDone, setRoadmapDone, params, onHome, onMenu }) {
  const firstStage = () => {
    if (params.openStep && ROADMAP.some((s) => s.k === params.openStep)) return params.openStep;
    const s = ROADMAP.find((st) => doneCount(st.k, roadmapDone) < tasksOf(st.k).length);
    return (s || ROADMAP[0]).k;
  };
  const [active, setActive] = useState(firstStage);
  const [stageOpen, setStageOpen] = useState(false);
  const [basis, setBasis] = useState(null);
  const [text, setText] = useState('');
  // 대화 속 코치 말풍선 · 할 일 카드. after = 그 시점까지 쌓인 질문·답 개수(그 뒤에 끼워 넣는다).
  const [events, setEvents] = useState([]);
  const chat = useChat('roadmap', user && user.id);
  const scrollRef = useRef(null);
  const seq = useRef(0);
  const started = useRef(false);

  const stage = ROADMAP.find((s) => s.k === active) || ROADMAP[0];
  const stageIdx = ROADMAP.indexOf(stage);
  const total = ROADMAP.reduce((n, s) => n + tasksOf(s.k).length, 0);
  const doneAll = ROADMAP.reduce((n, s) => n + doneCount(s.k, roadmapDone), 0);
  const pct = total ? Math.round((doneAll / total) * 100) : 0;
  const stageDone = doneCount(active, roadmapDone);

  const push = (...evs) => setEvents((cur) => [
    ...cur,
    ...evs.map((e) => ({ ...e, id: ++seq.current, after: chat.rows.length })),
  ]);

  // 대화 기록을 불러온 뒤 인사와 현재 단계 카드를 한 번 띄운다.
  useEffect(() => {
    if (!chat.ready || started.current) return;
    started.current = true;
    push(
      { kind: 'coach', text: `지금은 **${stage.phase} · ${stage.t}** 단계예요. 아래 할 일을 하나씩 체크해 보세요. 막히는 작업은 바로 물어보셔도 돼요.` },
      { kind: 'card', stage: stage.k },
    );
  }, [chat.ready]);

  // 새 말풍선 · 카드가 생기면 맨 아래로
  const lastRow = chat.rows[chat.rows.length - 1];
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    // 멀리 떨어져 있으면(긴 카드가 붙은 경우 등) 부드러운 스크롤이 늦어지므로 바로 이동한다.
    const far = el.scrollHeight - el.clientHeight - el.scrollTop > 1200;
    el.scrollTo({ top: el.scrollHeight, behavior: far ? 'auto' : 'smooth' });
  }, [events.length, chat.rows.length, lastRow && lastRow.answer]);

  // 바깥을 누르면 단계 목록을 닫는다.
  useEffect(() => {
    if (!stageOpen) return undefined;
    const close = (e) => {
      if (!e.target.closest('.m-rm-pop, .m-rm-strip__name')) setStageOpen(false);
    };
    document.addEventListener('pointerdown', close);
    return () => document.removeEventListener('pointerdown', close);
  }, [stageOpen]);

  const toggle = (key) => setRoadmapDone((cur) => ({ ...cur, [key]: !cur[key] }));
  const showCard = (k = active) => push({ kind: 'card', stage: k });
  const moveTo = (k) => {
    setStageOpen(false);
    if (k === active) { showCard(k); return; }
    const s = ROADMAP.find((x) => x.k === k);
    setActive(k);
    push({ kind: 'coach', text: `**${s.phase} · ${s.t}** 단계로 이동했어요. ${s.d}.` }, { kind: 'card', stage: k });
  };
  const send = (q, stageKey = active) => {
    const v = String(q || '').trim();
    if (!v || chat.busy) return;
    chat.send(v, { roadmapStep: stageKey });
    setText('');
  };
  const askRemaining = (s) => {
    const left = tasksOf(s.k).filter((_, i) => !roadmapDone[`${s.k}:${i}`]).map((t) => t.t);
    send(`'${s.t}' 단계에서 남은 작업(${left.join(', ')})을 어떻게 진행하면 좋을까요?`, s.k);
  };

  // 질문·답 사이사이에 코치 말풍선과 카드를 끼워 넣은 대화 목록
  const timeline = useMemo(() => {
    const out = [];
    for (let i = 0; i <= chat.rows.length; i += 1) {
      events.filter((e) => e.after === i).forEach((e) => out.push(e));
      if (i < chat.rows.length) out.push({ kind: 'qa', row: chat.rows[i], id: 'r' + chat.rows[i].id });
    }
    return out;
  }, [events, chat.rows]);

  const stateOf = (s) => {
    const n = doneCount(s.k, roadmapDone);
    if (s.k === active) return 'is-current';
    if (n === tasksOf(s.k).length && n > 0) return 'is-done';
    if (n > 0) return 'is-doing';
    return '';
  };

  return (
    <div className="m-screen m-rm">
      <div className="m-rm-top">
        <header className="m-rm-head">
          <MLogo onClick={onHome} />
          {/* 다른 화면과 같은 전체 화면 메뉴(01~06)를 연다 */}
          <button type="button" className="m-rm-head__menu" aria-label="메뉴" onClick={() => { setStageOpen(false); onMenu(); }}>
            <span /><span /><span />
          </button>
        </header>

        <div className="m-rm-strip">
          <div className="m-rm-strip__bar" role="tablist" aria-label="단계">
            {ROADMAP.map((s, i) => (
              <button key={s.k} type="button" role="tab" aria-selected={s.k === active}
                className={stateOf(s)} onClick={() => moveTo(s.k)} aria-label={`${i + 1}단계 ${s.t}`} />
            ))}
          </div>
          <div className="m-rm-strip__row">
            <button type="button" className="m-rm-strip__name" aria-expanded={stageOpen}
              onClick={() => setStageOpen((v) => !v)}>
              <span>{stage.phase} · {stageIdx + 1}/{ROADMAP.length}단계 · 전체 {pct}%</span>
              <b>{stage.t} <i aria-hidden="true">▾</i></b>
            </button>
            <button type="button" className="m-rm-strip__todo" onClick={() => showCard()}>
              할 일 {stageDone}/{tasksOf(active).length}
            </button>
          </div>
          {stageOpen && <div className="m-rm-dim" aria-hidden="true" />}
          {stageOpen && (
            <div className="m-rm-pop m-rm-pop--stage" role="listbox" aria-label="단계 목록">
              {ROADMAP.map((s, i) => {
                const n = doneCount(s.k, roadmapDone);
                return (
                  <button key={s.k} type="button" role="option" aria-selected={s.k === active}
                    className={s.k === active ? 'is-on' : ''} onClick={() => moveTo(s.k)}>
                    <span className={'m-rm-pop__dot ' + stateOf(s)}>{i + 1}</span>
                    <span className="m-rm-pop__name"><small>{s.phase}</small>{s.t}</span>
                    <span className="m-rm-pop__n">{n}/{tasksOf(s.k).length}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <div className="m-rm-chat" ref={scrollRef}>
        {!chat.ready && <div className="m-rm-msg is-coach"><span className="m-typing" aria-label="불러오는 중"><i /><i /><i /></span></div>}
        {timeline.map((e) => {
          if (e.kind === 'coach') return <div key={e.id} className="m-rm-msg is-coach"><Markdown text={e.text} /></div>;
          if (e.kind === 'card') {
            const s = ROADMAP.find((x) => x.k === e.stage);
            return <TaskCard key={e.id} stage={s} done={roadmapDone} onToggle={toggle} onBasis={setBasis} onAsk={askRemaining} />;
          }
          const r = e.row;
          return (
            <React.Fragment key={e.id}>
              <div className="m-rm-msg is-me">{r.question}</div>
              <div className="m-rm-msg is-coach">
                {r.pending && !r.answer
                  ? <span className="m-typing" aria-label="답변 작성 중"><i /><i /><i /></span>
                  : <Markdown text={r.answer || ''} />}
              </div>
            </React.Fragment>
          );
        })}
      </div>

      <div className="m-rm-input">
        <div className="m-rm-sugg">
          {SUGGESTIONS.map((q) => (
            <button key={q} type="button" onClick={() => send(q)} disabled={chat.busy}>{q}</button>
          ))}
        </div>
        <div className="m-rm-input__row">
          <button type="button" className="m-rm-input__card" onClick={() => showCard()} aria-label="이 단계 할 일 카드 보기">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6.5 5.5 8 8.5 5M4 12.5 5.5 14 8.5 11M4 18.5 5.5 20 8.5 17M11.5 6.5H20M11.5 12.5H20M11.5 18.5H20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </button>
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="로드맵 코치에게 물어보세요" aria-label="메시지"
            onKeyDown={(e) => {
              // 한글 조합 중 Enter는 글자 확정용이므로 전송하지 않는다.
              if (e.key === 'Enter' && !e.nativeEvent.isComposing && e.keyCode !== 229) { e.preventDefault(); send(text); }
            }} />
          <button type="button" className={'m-rm-input__send' + (text.trim() ? ' is-on' : '')} onClick={() => send(text)}
            disabled={!text.trim() || chat.busy} aria-label="전송">
            <SendIcon />
          </button>
        </div>
      </div>

      <Sheet open={!!basis} onClose={() => setBasis(null)} title={basis ? basis.t : ''}>
        {basis && (
          <>
            <span className="m-tag">{basis.grade}</span>
            {RM_GRADES[basis.grade] && <p className="m-sheet__sub">{RM_GRADES[basis.grade].desc}</p>}
            <p className="m-sheet__text">{basis.basis}</p>
            {(basis.src || []).filter(Boolean).map((src) => (
              <a key={src.url} className="m-sheet__link" href={src.url} target="_blank" rel="noreferrer">{src.label} ↗</a>
            ))}
          </>
        )}
      </Sheet>
    </div>
  );
}
