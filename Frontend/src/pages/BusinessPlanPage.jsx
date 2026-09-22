import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api.js';
import { linkBtn } from '../utils.js';

const IDEA_FIELDS = [
  { key: 'targetCustomer', label: '목표 고객', placeholder: '누구를 위한 사업인가요?' },
  { key: 'problem', label: '핵심 문제', placeholder: '그 고객이 겪는 문제는 무엇인가요?' },
  { key: 'solution', label: '해결 방안', placeholder: '어떻게 해결하나요? 제품·서비스의 핵심 기능은?' },
  { key: 'differentiator', label: '차별점', placeholder: '경쟁 서비스와 다른 점은 무엇인가요? (선택)' },
  { key: 'team', label: '팀 구성', placeholder: '누가, 어떤 역할로 함께하나요? (선택)' },
];

const EMPTY_FORM = {
  businessName: '', tagline: '', targetProgram: '', extraNotes: '', templateText: '',
  targetCustomer: '', problem: '', solution: '', differentiator: '', team: '',
};

// 기본 PSST 4축 — 지원사업 공고 양식을 넣지 않았을 때 AI가 따르는 구조이자,
// 초안을 만들기 전 왼쪽 네비게이션에 보여줄 미리보기 항목이다.
const DEFAULT_SECTION_META = {
  problem: { label: 'Problem · 문제인식', desc: '어떤 고객이 어떤 문제를 겪고 있는지, 왜 지금 해결해야 하는지를 설명해요.' },
  solution: { label: 'Solution · 실현가능성', desc: '그 문제를 어떻게 해결하는지, 제품·서비스의 핵심 기능과 차별점을 설명해요.' },
  scaleUp: { label: 'Scale-up · 성장전략', desc: '목표 시장과 고객 확보 방법, 수익모델을 어떻게 키울지 설명해요.' },
  team: { label: 'Team · 팀구성', desc: '팀 구성과 이 팀이 이 사업을 해낼 수 있는 이유를 설명해요.' },
};
const DEFAULT_SECTIONS = Object.keys(DEFAULT_SECTION_META).map((key) => ({
  key, label: DEFAULT_SECTION_META[key].label,
}));
const GENERIC_SECTION_DESC = 'AI가 지원사업 공고 양식에 맞춰 쓴 초안이에요. 필요하면 직접 고쳐 써도 되고, 오른쪽 아이디어 어시스턴트에게 다듬어 달라고 물어봐도 좋아요.';

// 왼쪽 사이드바 그룹 구조 — Gixpert의 "준비 / AI 설계 / 마무리" 3단 구조를 참고했다.
// "AI 설계" 항목은 고정이 아니라 plan.sections(초안 생성 결과)를 따라 개수·제목이 바뀐다.
function buildGroups(aiSteps) {
  return [
    { name: '준비', steps: [
      { key: 'basic', label: '기초 정보' },
      { key: 'idea', label: '아이디어 정리' },
    ] },
    { name: 'AI 설계', steps: aiSteps },
    { name: '마무리', steps: [
      { key: 'evaluate', label: 'AI 예비진단' },
      { key: 'done', label: '완료 · 다운로드' },
    ] },
  ];
}

const CHAT_SUGGESTIONS = [
  '우리 제품의 핵심 문제점은 무엇인가요?',
  '이 문제를 해결할 아이디어를 제안해줘',
  '팀구성에서 어떤 내용을 강조하면 좋을까?',
];

const DRAFT_KEY = (userId) => `changeup:bizplan-draft:${userId}`;

function loadDraft(userId) {
  try {
    const raw = JSON.parse(localStorage.getItem(DRAFT_KEY(userId)) || 'null');
    return raw && typeof raw === 'object' ? raw : null;
  } catch (e) {
    return null;
  }
}
function saveDraft(userId, draft) {
  try {
    localStorage.setItem(DRAFT_KEY(userId), JSON.stringify(draft));
  } catch (e) {
    /* 저장 불가 환경은 무시 */
  }
}

function scoreTone(score) {
  if (score >= 80) return 'good';
  if (score >= 60) return 'warn';
  return 'bad';
}

function planToMarkdown(form, plan) {
  const lines = [
    `# ${form.businessName || '사업계획서'} 초안`,
    '',
    form.tagline ? `> ${form.tagline}` : '',
    '',
    '## 세 줄 요약',
    plan.summary,
    '',
  ];
  (plan.sections || []).forEach((s) => {
    lines.push(`## ${s.label}`, s.content, '');
  });
  lines.push('---', 'AI가 입력한 내용만으로 작성한 초안입니다. 수치·실적은 직접 확인해 채우고, 제출 전 검토해 주세요.');
  return lines.filter((l) => l !== undefined).join('\n');
}

function downloadMarkdown(form, plan) {
  const text = planToMarkdown(form, plan);
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${(form.businessName || '사업계획서').replace(/[\\/:*?"<>|]/g, '')}_사업계획서.md`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function AnalyzingPanel({ title, sub }) {
  return (
    <div className="exp-ai" role="status" aria-live="polite">
      <span className="exp-ai__glow exp-ai__glow--a" aria-hidden="true" />
      <span className="exp-ai__glow exp-ai__glow--b" aria-hidden="true" />
      <div className="exp-ai__orb" aria-hidden="true">
        <span className="exp-ai__orb-ring" />
        <span className="exp-ai__orb-core" />
      </div>
      <div className="exp-ai__text">
        <p className="exp-ai__title">{title}</p>
        <p className="exp-ai__sub">{sub}</p>
      </div>
    </div>
  );
}

function ScoreGauge({ score }) {
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div className={'bp-gauge bp-gauge--' + scoreTone(pct)} style={{ '--pct': pct }}>
      <span className="bp-gauge__num">{pct}</span>
      <span className="bp-gauge__unit">점</span>
    </div>
  );
}

// 오른쪽에 항상 붙어 있는 "아이디어 어시스턴트". 대화는 저장하지 않고 이 화면을 떠나면 사라진다.
function IdeaAssistant({ form, plan }) {
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const bodyRef = useRef(null);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [messages, busy]);

  const send = async (text) => {
    const q = (text || '').trim();
    if (!q || busy) return;
    setErr('');
    setDraft('');
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((cur) => [...cur, { role: 'user', content: q }]);
    setBusy(true);
    try {
      const res = await api.bizplanCoach({
        question: q,
        businessName: form.businessName,
        tagline: form.tagline,
        targetCustomer: form.targetCustomer,
        sections: (plan && plan.sections) || [],
        conversationHistory: history,
      });
      setMessages((cur) => [...cur, { role: 'assistant', content: res.answer, redirect: res.redirect }]);
    } catch (e2) {
      setErr('지금은 답변을 받지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="bp-chat">
      <div className="bp-chat__head">
        <span className="bp-chat__dot" aria-hidden="true" />
        <b>AI 어시스턴트</b>
        <button type="button" className="bp-chat__new" onClick={() => setMessages([])}>+ 새 채팅</button>
      </div>
      <div className="bp-chat__body" ref={bodyRef}>
        {messages.length === 0 ? (
          <div className="bp-chat__intro">
            <span className="bp-chat__icon" aria-hidden="true">✨</span>
            <b>아이디어 어시스턴트</b>
            <p>기업의 제품·아이디어를 바탕으로 문제인식과 해결 방안을 구체화하도록 도와드려요.</p>
            <div className="bp-chat__chips">
              {CHAT_SUGGESTIONS.map((s) => (
                <button key={s} type="button" className="bp-chat__chip" onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, i) => (
            <div key={i} className={'bp-chat__msg bp-chat__msg--' + m.role}>
              {m.content}
              {m.redirect && m.redirect !== 'none' && (
                <span className="bp-chat__redirect">
                  {m.redirect === 'tax' ? 'AI 세무 Assistant' : '공고지원 AI'}로 이동해 확인해 보세요.
                </span>
              )}
            </div>
          ))
        )}
        {busy && (
          <div className="bp-chat__msg bp-chat__msg--assistant bp-chat__typing">
            <span className="typing" aria-hidden="true"><i /><i /><i /></span>
          </div>
        )}
      </div>
      {err && <p className="cal__err" style={{ margin: '0 12px 8px' }}>{err}</p>}
      <form className="bp-chat__foot" onSubmit={(e) => { e.preventDefault(); send(draft); }}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="AI에게 질문하세요"
          aria-label="아이디어 어시스턴트에게 질문"
          disabled={busy}
        />
        <button type="submit" aria-label="보내기" disabled={busy || !draft.trim()}>↑</button>
      </form>
      <p className="bp-chat__disc">AI 응답은 참고용이니 중요한 내용은 검토 후 활용해 주세요</p>
    </aside>
  );
}

export function BusinessPlanPage({ user, onRequireLogin }) {
  const userId = user && user.id;
  const [active, setActive] = useState('basic');
  const [form, setForm] = useState(EMPTY_FORM);
  const [plan, setPlan] = useState(null); // { sections: [{key,label,content}], summary, llmUsed }
  const [evalResult, setEvalResult] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [err, setErr] = useState('');
  const [savedNote, setSavedNote] = useState('');

  // 로그인한 사용자의 임시저장 초안을 불러온다.
  useEffect(() => {
    if (!userId) return;
    const draft = loadDraft(userId);
    if (draft) {
      setForm({ ...EMPTY_FORM, ...(draft.form || {}) });
      if (draft.plan && Array.isArray(draft.plan.sections)) setPlan(draft.plan);
      if (draft.evalResult) setEvalResult(draft.evalResult);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const setField = (key, value) => setForm((f) => ({ ...f, [key]: value }));
  const setSectionContent = (key, content) =>
    setPlan((p) => (p ? { ...p, sections: p.sections.map((s) => (s.key === key ? { ...s, content } : s)) } : p));

  const ideaReady = form.targetCustomer.trim() && form.problem.trim() && form.solution.trim();
  const usingTemplate = !!form.templateText.trim();

  // 초안이 아직 없으면 기본 PSST 4항목을 미리보기로 보여주고, 생성되고 나면 실제 결과(공고
  // 양식을 넣었다면 그 항목 구성)로 자연스럽게 바뀐다.
  const aiSteps = plan && plan.sections && plan.sections.length
    ? plan.sections.map((s) => ({ key: s.key, label: s.label }))
    : DEFAULT_SECTIONS;
  const aiStepKeys = aiSteps.map((s) => s.key);
  const GROUPS = buildGroups(aiSteps);
  const ALL_STEPS = GROUPS.flatMap((g) => g.steps);

  const stepDone = (key) => {
    if (key === 'basic') return !!(form.businessName.trim() && form.tagline.trim());
    if (key === 'idea') return !!ideaReady;
    if (aiStepKeys.includes(key)) {
      const section = plan && plan.sections && plan.sections.find((s) => s.key === key);
      return !!(section && section.content.trim());
    }
    if (key === 'evaluate') return !!evalResult;
    if (key === 'done') return !!evalResult;
    return false;
  };

  const generatePlan = async () => {
    if (!userId) {
      onRequireLogin && onRequireLogin();
      return;
    }
    if (!ideaReady) {
      setActive('idea');
      setErr('목표 고객, 핵심 문제, 해결 방안을 먼저 입력해 주세요.');
      return;
    }
    setErr('');
    setGenerating(true);
    try {
      const res = await api.generateBusinessPlan(form);
      setPlan(res);
      setEvalResult(null);
      setActive((res.sections && res.sections[0] && res.sections[0].key) || 'basic');
    } catch (e2) {
      if (e2 && e2.status === 401) onRequireLogin && onRequireLogin();
      else setErr('초안을 만들지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setGenerating(false);
    }
  };

  const runEvaluate = async () => {
    if (!plan) return;
    setErr('');
    setEvaluating(true);
    try {
      const res = await api.evaluateBusinessPlan({ sections: plan.sections });
      setEvalResult(res);
    } catch (e2) {
      if (e2 && e2.status === 401) onRequireLogin && onRequireLogin();
      else setErr('예비진단을 실행하지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setEvaluating(false);
    }
  };

  const goStep = (key) => {
    setErr('');
    setActive(key);
    if (aiStepKeys.includes(key) && !plan && !generating) generatePlan();
  };

  const saveNow = () => {
    if (!userId) {
      onRequireLogin && onRequireLogin();
      return;
    }
    saveDraft(userId, { form, plan, evalResult });
    setSavedNote('임시저장했어요');
    setTimeout(() => setSavedNote(''), 2000);
  };

  const activeIdx = ALL_STEPS.findIndex((s) => s.key === active);
  const nextStep = ALL_STEPS[activeIdx + 1];
  const activeSection = plan && plan.sections && plan.sections.find((s) => s.key === active);

  if (!userId) {
    return (
      <div className="tool">
        <div className="tool__panel">
          <h2>사업계획서 초안</h2>
          <p className="cvx__empty">
            로그인하면 사업계획서 초안을 만들 수 있어요.{' '}
            {onRequireLogin && (
              <button type="button" style={linkBtn} onClick={onRequireLogin}>로그인</button>
            )}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bp2">
      <div className="bp2__top">
        <input
          className="bp2__title"
          value={form.businessName}
          onChange={(e) => setField('businessName', e.target.value)}
          placeholder="사업계획서의 제목(사업명)을 입력하세요."
          aria-label="사업명"
        />
        <div className="bp2__topactions">
          {savedNote && <span className="bp2__saved">{savedNote}</span>}
          <button type="button" className="bp2__save" onClick={saveNow}>임시저장</button>
          {nextStep && (
            <button type="button" className="bp2__next" onClick={() => goStep(nextStep.key)}>
              다음 단계 · {nextStep.label} ›
            </button>
          )}
        </div>
      </div>

      <div className="bp2__body">
        <nav className="bp2__nav" aria-label="사업계획서 작성 단계">
          {GROUPS.map((g) => {
            const doneCount = g.steps.filter((s) => stepDone(s.key)).length;
            return (
              <div key={g.name} className="bp2__group">
                <div className="bp2__grouphead">
                  <span>{g.name}</span>
                  <span className="bp2__groupcount">{doneCount}/{g.steps.length}</span>
                </div>
                {g.steps.map((s) => (
                  <button
                    key={s.key}
                    type="button"
                    className={'bp2__navitem' + (active === s.key ? ' is-active' : '')}
                    onClick={() => goStep(s.key)}
                  >
                    <span className={'bp2__navcheck' + (stepDone(s.key) ? ' is-done' : '')} aria-hidden="true">
                      {stepDone(s.key) ? '✔' : ''}
                    </span>
                    {s.label}
                  </button>
                ))}
              </div>
            );
          })}
        </nav>

        <main className="bp2__main">
          {err && <p className="cal__err">{err}</p>}

          {active === 'basic' && (
            <section>
              <h3 className="bp2__stepttl">기초 정보</h3>
              <p className="bp2__stepdesc">사업의 기본 정보예요. 계획서 표지와 개요에 반영돼요.</p>
              <label className="bp-field">
                <span className="bp-field__label">한 줄 소개</span>
                <input type="text" value={form.tagline} placeholder="예: 소규모 매장을 위한 재고관리 앱"
                  onChange={(e) => setField('tagline', e.target.value)} />
              </label>
              <label className="bp-field">
                <span className="bp-field__label">신청하려는 지원사업 (선택)</span>
                <input type="text" value={form.targetProgram} placeholder="예: 예비창업패키지"
                  onChange={(e) => setField('targetProgram', e.target.value)} />
              </label>
              <label className="bp-field">
                <span className="bp-field__label">
                  지원사업 공고 양식 (선택)
                  <em className="bp-field__sub">넣으면 그 양식에 맞춰 작성해요</em>
                </span>
                <textarea rows={5} value={form.templateText}
                  placeholder={'공고에 나온 사업계획서 항목 구성을 그대로 붙여넣으세요.\n예)\n1. 창업아이템 개요\n2. 개발 동기 및 목적\n3. 시장분석 및 경쟁력 확보방안\n4. 사업화 추진전략'}
                  onChange={(e) => setField('templateText', e.target.value)} />
              </label>
              <p className="bp-hint">
                {usingTemplate
                  ? '공고 양식을 넣었어요 — AI 설계 단계에서 이 양식의 항목 구성 그대로 초안을 만들어요.'
                  : '비워두면 기본 PSST(문제인식·실현가능성·성장전략·팀구성) 구조로 만들어요.'}
              </p>
              <label className="bp-field">
                <span className="bp-field__label">추가로 참고할 내용 (선택)</span>
                <textarea rows={2} value={form.extraNotes} placeholder="초안에 반영했으면 하는 내용"
                  onChange={(e) => setField('extraNotes', e.target.value)} />
              </label>
            </section>
          )}

          {active === 'idea' && (
            <section>
              <h3 className="bp2__stepttl">아이디어 정리</h3>
              <p className="bp2__stepdesc">사업 아이디어를 구체화해요. AI 초안의 '문제인식·실현가능성' 항목에 반영돼요.</p>
              {IDEA_FIELDS.map((f) => (
                <label key={f.key} className="bp-field">
                  <span className="bp-field__label">{f.label}</span>
                  <textarea rows={2} value={form[f.key]} placeholder={f.placeholder}
                    onChange={(e) => setField(f.key, e.target.value)} />
                </label>
              ))}
              <button type="button" className="exp-upload" onClick={generatePlan} disabled={!ideaReady || generating}>
                ✨ AI로 초안 만들기 →
              </button>
              {!ideaReady && <p className="bp-hint">목표 고객, 핵심 문제, 해결 방안은 꼭 입력해 주세요.</p>}
            </section>
          )}

          {aiStepKeys.includes(active) && (
            <section>
              <h3 className="bp2__stepttl">
                {(activeSection && activeSection.label) || DEFAULT_SECTION_META[active]?.label || active}
              </h3>
              <p className="bp2__stepdesc">
                {DEFAULT_SECTION_META[active]?.desc || GENERIC_SECTION_DESC}
              </p>
              {generating ? (
                <AnalyzingPanel
                  title="AI가 초안을 쓰고 있어요"
                  sub={usingTemplate ? '지원사업 공고 양식의 항목 구성에 맞춰 정리하고 있어요…' : '문제인식 · 실현가능성 · 성장전략 · 팀구성 순서로 정리하고 있어요…'}
                />
              ) : activeSection ? (
                <React.Fragment>
                  <textarea
                    className="bp2__psst-textarea"
                    rows={10}
                    value={activeSection.content}
                    onChange={(e) => setSectionContent(active, e.target.value)}
                  />
                  <p className="bp-hint">필요하면 직접 고쳐도 돼요. 오른쪽 아이디어 어시스턴트에게 다듬어 달라고 물어봐도 좋아요.</p>
                </React.Fragment>
              ) : (
                <div className="bp2__empty">
                  <p>아직 AI 초안이 없어요. 먼저 아이디어를 정리하고 초안을 만들어 주세요.</p>
                  <button type="button" className="exp-upload" onClick={() => goStep('idea')}>← 아이디어 정리로 이동</button>
                </div>
              )}
            </section>
          )}

          {active === 'evaluate' && (
            <section className="bp-eval">
              <h3 className="bp2__stepttl">AI 예비진단</h3>
              <p className="bp2__stepdesc">완성된 초안을 AI가 항목별로 미리 채점해요. 실제 심사 결과를 보장하지 않는 참고용이에요.</p>

              {!plan ? (
                <div className="bp2__empty">
                  <p>먼저 AI 초안을 만들어야 예비진단을 받을 수 있어요.</p>
                  <button type="button" className="exp-upload" onClick={() => goStep('idea')}>← 아이디어 정리로 이동</button>
                </div>
              ) : evaluating ? (
                <AnalyzingPanel title="AI가 예비진단을 하고 있어요" sub="항목별로 강점과 보완할 점을 살펴보고 있어요…" />
              ) : !evalResult ? (
                <button type="button" className="exp-upload" onClick={runEvaluate}>🩺 예비진단 시작하기</button>
              ) : (
                <React.Fragment>
                  <div className="bp-eval__summary">
                    <ScoreGauge score={evalResult.overallScore} />
                    <div>
                      <p className="bp-eval__ttl">종합 평가</p>
                      <p className="bp-eval__comment">{evalResult.overallComment}</p>
                    </div>
                  </div>
                  <ul className="bp-eval__list">
                    {evalResult.sections.map((s) => (
                      <li key={s.key} className={'bp-eval__row bp-eval__row--' + scoreTone(s.score)}>
                        <div className="bp-eval__rowhead">
                          <span className="bp-eval__rowlabel">{s.label || s.key}</span>
                          <span className="bp-eval__rowscore">{s.score}점</span>
                        </div>
                        <div className="bp-eval__bar"><i style={{ width: s.score + '%' }} /></div>
                        <p className="bp-eval__pos">👍 {s.strengths}</p>
                        <p className="bp-eval__neg">🔧 {s.improvements}</p>
                      </li>
                    ))}
                  </ul>
                  <p className="bp-disclaimer">
                    실제 심사 결과가 아니라 AI가 초안만 보고 매긴 참고용 자체 점검이에요. 지원사업마다 평가
                    기준이 다르니 제출 전 세무사·창업지원기관 등 전문가 검토를 함께 받아 보세요.
                  </p>
                  <button type="button" className="exp-excel" onClick={runEvaluate}>🔄 다시 진단받기</button>
                </React.Fragment>
              )}
            </section>
          )}

          {active === 'done' && (
            <section>
              <h3 className="bp2__stepttl">완료 · 다운로드</h3>
              {!plan ? (
                <div className="bp2__empty">
                  <p>아직 완성된 초안이 없어요.</p>
                  <button type="button" className="exp-upload" onClick={() => goStep('idea')}>← 아이디어 정리로 이동</button>
                </div>
              ) : (
                <React.Fragment>
                  <p className="bp2__stepdesc">
                    {evalResult
                      ? `AI 예비진단 총점 ${evalResult.overallScore}점의 초안이에요. 파일로 내려받아 제출 전 검토에 활용하세요.`
                      : '초안이 준비됐어요. AI 예비진단을 받아 보거나 바로 내려받을 수 있어요.'}
                  </p>
                  <p className="bp-summary">{plan.summary}</p>
                  <div className="bp-actions">
                    {!evalResult && (
                      <button type="button" className="bp-back" onClick={() => goStep('evaluate')}>🩺 예비진단 받으러 가기</button>
                    )}
                    <button type="button" className="exp-upload" onClick={() => downloadMarkdown(form, plan)}>
                      📄 사업계획서 다운로드 (.md)
                    </button>
                  </div>
                  <p className="bp-disclaimer">
                    AI가 입력한 내용만으로 작성한 초안이에요. [직접 채워 주세요] 표시는 사실 확인이 필요한
                    자리이니 채워 넣고, 제출 전에 다시 검토해 주세요. 한글(HWP)·PDF 다운로드는 아직 준비 중이에요.
                  </p>
                </React.Fragment>
              )}
            </section>
          )}
        </main>

        <IdeaAssistant form={form} plan={plan} />
      </div>
    </div>
  );
}
