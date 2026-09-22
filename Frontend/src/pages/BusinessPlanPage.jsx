import React, { useState } from 'react';
import { api } from '../api.js';
import { linkBtn } from '../utils.js';

const FIELDS = [
  { key: 'businessName', label: '사업명', placeholder: '예: 동네사장', type: 'text' },
  { key: 'tagline', label: '한 줄 소개', placeholder: '예: 소규모 매장을 위한 재고관리 앱', type: 'text' },
  { key: 'targetCustomer', label: '목표 고객', placeholder: '누구를 위한 사업인가요?', type: 'textarea' },
  { key: 'problem', label: '핵심 문제', placeholder: '그 고객이 겪는 문제는 무엇인가요?', type: 'textarea' },
  { key: 'solution', label: '해결 방안', placeholder: '어떻게 해결하나요? 제품·서비스의 핵심 기능은?', type: 'textarea' },
  { key: 'differentiator', label: '차별점', placeholder: '경쟁 서비스와 다른 점은 무엇인가요?', type: 'textarea' },
  { key: 'team', label: '팀 구성', placeholder: '누가, 어떤 역할로 함께하나요?', type: 'textarea' },
  { key: 'targetProgram', label: '신청하려는 지원사업 (선택)', placeholder: '예: 예비창업패키지', type: 'text' },
  { key: 'extraNotes', label: '추가로 참고할 내용 (선택)', placeholder: '초안에 반영했으면 하는 내용', type: 'textarea' },
];

const EMPTY_FORM = FIELDS.reduce((acc, f) => ({ ...acc, [f.key]: '' }), {});

const PSST_SECTIONS = [
  { key: 'problem', label: 'Problem · 문제 인식' },
  { key: 'solution', label: 'Solution · 실현 가능성' },
  { key: 'scaleUp', label: 'Scale-up · 성장 전략' },
  { key: 'team', label: 'Team · 팀 구성' },
];

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
  PSST_SECTIONS.forEach((s) => {
    lines.push(`## ${s.label}`, plan[s.key], '');
  });
  lines.push(
    '---',
    'AI가 입력한 내용만으로 작성한 초안입니다. 수치·실적은 직접 확인해 채우고, 제출 전 검토해 주세요.'
  );
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

export function BusinessPlanPage({ user, onRequireLogin }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [plan, setPlan] = useState(null); // { problem, solution, scaleUp, team, summary, llmUsed }
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const userId = user && user.id;

  const setField = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  const canSubmit =
    form.targetCustomer.trim() && form.problem.trim() && form.solution.trim() && !busy;

  const generate = async (e) => {
    e.preventDefault();
    if (!userId) {
      onRequireLogin && onRequireLogin();
      return;
    }
    if (!canSubmit) return;
    setBusy(true);
    setErr('');
    try {
      const res = await api.generateBusinessPlan(form);
      setPlan(res);
    } catch (e2) {
      if (e2 && e2.status === 401) onRequireLogin && onRequireLogin();
      else setErr('초안을 만들지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setBusy(false);
    }
  };

  const setPlanField = (key, value) => setPlan((p) => ({ ...p, [key]: value }));

  return (
    <div className="tool">
      <div className="tool__panel">
        <h2>사업계획서 초안</h2>
        <p style={{ margin: '0 0 14px', fontSize: 12.5, color: 'var(--ink-soft)' }}>
          아래 내용을 입력하면 AI가 PSST(문제·해결·성장전략·팀) 구조의 초안을 만들어 드려요.
          입력하지 않은 사실(매출액, 이용자 수 등)은 지어내지 않고 빈 자리로 남겨 둡니다.
          제출 전 사실 확인과 검토가 필요해요.
        </p>

        {!userId ? (
          <p className="cvx__empty">
            로그인하면 사업계획서 초안을 만들 수 있어요.{' '}
            {onRequireLogin && (
              <button type="button" style={linkBtn} onClick={onRequireLogin}>로그인</button>
            )}
          </p>
        ) : (
          <form className="bp-form" onSubmit={generate}>
            {FIELDS.map((f) => (
              <label key={f.key} className="bp-field">
                <span className="bp-field__label">{f.label}</span>
                {f.type === 'textarea' ? (
                  <textarea
                    rows={2}
                    value={form[f.key]}
                    placeholder={f.placeholder}
                    onChange={(e2) => setField(f.key, e2.target.value)}
                  />
                ) : (
                  <input
                    type="text"
                    value={form[f.key]}
                    placeholder={f.placeholder}
                    onChange={(e2) => setField(f.key, e2.target.value)}
                  />
                )}
              </label>
            ))}
            <button type="submit" className="exp-upload" disabled={!canSubmit}>
              {busy ? 'AI가 초안을 쓰고 있어요…' : '✨ AI로 초안 만들기'}
            </button>
            {!form.targetCustomer.trim() || !form.problem.trim() || !form.solution.trim() ? (
              <p className="bp-hint">목표 고객, 핵심 문제, 해결 방안은 꼭 입력해 주세요.</p>
            ) : null}
          </form>
        )}

        {err && <p className="cal__err">{err}</p>}

        {plan && (
          <div className="bp-result">
            <div className="bp-result__head">
              <h3>초안이 만들어졌어요</h3>
              <button type="button" className="exp-excel" onClick={() => downloadMarkdown(form, plan)}>
                📄 다운로드 (.md)
              </button>
            </div>
            <p className="bp-summary">{plan.summary}</p>
            {PSST_SECTIONS.map((s) => (
              <label key={s.key} className="bp-field">
                <span className="bp-field__label">{s.label}</span>
                <textarea
                  rows={4}
                  value={plan[s.key] || ''}
                  onChange={(e2) => setPlanField(s.key, e2.target.value)}
                />
              </label>
            ))}
            <p className="bp-disclaimer">
              AI가 입력한 내용만으로 작성한 초안이에요. 수치·실적처럼 직접 확인해야 하는 값은
              [직접 채워 주세요] 형태로 비워 두었으니 채워 넣고, 제출 전에 다시 검토해 주세요.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
