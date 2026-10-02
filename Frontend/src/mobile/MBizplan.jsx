// 04 사업계획서(1단계 계획 정리): 5단계 진행 바 → 항목 세그먼트 → 입력칸(남은 높이를 나눠 가짐)
// → AI로 PSST 초안 정리하기 → 임시저장 · 다음. 저장 형식은 PC 화면과 같은 임시저장·보관함 API를 쓴다.
import React, { useEffect, useState } from 'react';
import { api } from '../api.js';
import { INDUSTRIES, REGIONS } from '../constants.js';
import { FeatureHeader, Seg, Sheet, featureOf, useToast } from './ui.jsx';

const STEPS = ['계획 정리', '양식 선택', '초안 평가', '초안 수정', '재평가'];
const SELECTS = {
  startupStatus: { label: '창업 상태', options: ['예비창업자', '개인사업자', '법인사업자'] },
  industry: { label: '업종', options: INDUSTRIES },
  businessRegion: { label: '사업 지역', options: ['전국', ...REGIONS] },
  businessType: { label: '사업 형태', options: ['1인 창업', '공동 창업', '온라인 서비스', '오프라인 매장', '온·오프라인 병행', '제품 제조·판매'] },
};
const TABS = [
  { key: 'basic', label: '기초 정보' },
  { key: 'customer', label: '고객', fields: [['targetCustomer', '목표 고객', '누구를 위한 사업인가요?']] },
  { key: 'problem', label: '문제', fields: [['problem', '핵심 문제', '그 고객이 겪는 문제는 무엇인가요?'], ['solution', '해결 방안', '그 문제를 어떻게 해결하나요?']] },
  { key: 'feature', label: '기능', fields: [['coreFeatures', '핵심 기능', '제품·서비스의 핵심 기능'], ['differentiator', '차별점', '기존 제품·서비스와 다른 점']] },
  { key: 'revenue', label: '수익', fields: [['revenueModel', '수익 방식', '예: 월 구독료, 판매 수수료']] },
  { key: 'extra', label: '추가 설명', fields: [['extraNotes', '추가 설명 (선택)', '초안에 더 반영할 내용']] },
];
const EMPTY = {
  businessName: '', startupStatus: '', industry: '', businessRegion: '', businessType: '', team: '',
  targetCustomer: '', problem: '', solution: '', coreFeatures: '', differentiator: '', revenueModel: '', extraNotes: '',
};
const REQUIRED = Object.keys(EMPTY).filter((k) => k !== 'extraNotes');

export function MBizplan({ user, onHome, onMenu, onLogin }) {
  const toast = useToast();
  const [tab, setTab] = useState('basic');
  const [form, setForm] = useState(EMPTY);
  const [draft, setDraft] = useState({});
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState('');
  const [nextOpen, setNextOpen] = useState(false);

  useEffect(() => {
    if (!user) return undefined;
    let alive = true;
    api.bizplanDraft()
      .then((r) => {
        if (!alive) return;
        const data = (r && r.data) || {};
        setDraft(data);
        setForm({ ...EMPTY, ...(data.form || {}) });
      })
      .catch(() => {})
      .finally(() => alive && setLoaded(true));
    return () => { alive = false; };
  }, [user]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const missing = REQUIRED.filter((k) => !String(form[k] || '').trim());

  // PC 화면의 임시저장과 같은 순서: 보관함(plans)에 저장해 ID를 받고, 그 ID를 넣어 작성 화면 임시저장.
  const persist = async (data) => {
    let id = Number.isInteger(data.planId) ? data.planId : null;
    const body = { ...data };
    delete body.planId;
    try {
      id = id ? (await api.saveBizplanPlan(id, body)).id : (await api.createBizplanPlan(body)).id;
    } catch (e) {
      if (!(e && e.status === 404)) throw e;
      id = (await api.createBizplanPlan(body)).id;
    }
    const next = { ...body, planId: id };
    await api.saveBizplanDraft(next);
    setDraft(next);
  };

  const save = async () => {
    if (busy) return;
    setBusy('save');
    try {
      await persist({ ...draft, form });
      toast('임시저장했어요');
    } catch (e) {
      if (e && e.status === 401) onLogin();
      else toast('임시저장하지 못했어요');
    } finally {
      setBusy('');
    }
  };

  const refine = async () => {
    if (busy) return;
    if (missing.length) {
      toast('추가 설명을 뺀 모든 칸을 채워 주세요');
      return;
    }
    setBusy('refine');
    try {
      const res = await api.refineBusinessPlan({ input: form });
      // 선택 항목(창업 상태·업종·지역·형태)은 사용자가 고른 값을 유지한다(PC와 같음).
      const keep = Object.fromEntries(Object.keys(SELECTS).map((k) => [k, form[k]]));
      const refined = { ...form, ...(res.refined || {}), ...keep };
      setForm(refined);
      // 내용이 바뀌었으므로 이전 초안·평가 결과는 비운다(PC와 같은 규칙).
      await persist({
        ...draft, form: refined, refinedDone: true, plan: null, evalResult: null, revisionSections: [],
        finalPlan: null, finalEvalResult: null, fieldAnalysis: [], supplementAnswers: {}, supplementImages: {},
        supplementChoices: {}, supplementPage: 0, editedSectionKeys: [],
      });
      toast('AI가 PSST 초안용으로 정리했어요');
    } catch (e) {
      if (e && e.status === 401) onLogin();
      else toast((e && e.detail) || '정리하지 못했어요. 잠시 후 다시 시도해 주세요');
    } finally {
      setBusy('');
    }
  };

  const current = TABS.find((t) => t.key === tab);
  let no = 0;
  const numbered = (label) => { no += 1; return <span className="m-no">{String(no).padStart(2, '0')}</span>; };

  return (
    <div className="m-screen">
      <FeatureHeader feature={featureOf('bizplan')} onHome={onHome} onMenu={onMenu} />
      <div className="m-body">
        <ol className="m-steps" aria-label="진행 단계">
          {STEPS.map((s, i) => (
            <li key={s} className={i === 0 ? 'is-on' : ''} aria-current={i === 0 ? 'step' : undefined}><i /><span>{s}</span></li>
          ))}
        </ol>
        <Seg className="m-seg--scroll" value={tab} onChange={setTab} items={TABS.map((t) => ({ key: t.key, label: t.label }))} />

        <section className="m-glass m-form">
          {!loaded && <p className="m-empty">불러오는 중…</p>}
          {loaded && tab === 'basic' && (
            <>
              <label className="m-field m-field--line">
                <span className="m-field__label">{numbered()}사업/아이템명</span>
                <input value={form.businessName} onChange={(e) => set('businessName', e.target.value)} placeholder="예: 소상공인 재고관리 서비스" />
              </label>
              <div className="m-field-grid">
                {Object.entries(SELECTS).map(([k, s]) => (
                  <label key={k} className="m-field m-field--line">
                    <span className="m-field__label">{numbered()}{s.label}</span>
                    <select value={form[k]} onChange={(e) => set(k, e.target.value)}>
                      <option value="" disabled>선택</option>
                      {form[k] && !s.options.includes(form[k]) && <option value={form[k]}>{form[k]}</option>}
                      {s.options.map((o) => <option key={o} value={o}>{o}</option>)}
                    </select>
                  </label>
                ))}
              </div>
              <label className="m-field m-field--grow">
                <span className="m-field__label">{numbered()}팀 구성</span>
                <textarea value={form.team} onChange={(e) => set('team', e.target.value)} placeholder="구성원과 담당 역할" />
              </label>
            </>
          )}
          {loaded && current.fields && current.fields.map(([k, label, hint]) => (
            <label key={k} className="m-field m-field--grow">
              <span className="m-field__label">{numbered()}{label}<em>{hint}</em></span>
              <textarea value={form[k]} onChange={(e) => set(k, e.target.value)} placeholder={hint} />
            </label>
          ))}
        </section>

        <button type="button" className="m-btn m-btn--primary" onClick={refine} disabled={!!busy || !loaded}>
          {busy === 'refine' ? 'AI가 정리하는 중…' : draft.refinedDone ? 'AI로 PSST 초안 다시 정리하기' : 'AI로 PSST 초안 정리하기'}
        </button>
        <div className="m-row2">
          <button type="button" className="m-btn m-btn--glass" onClick={save} disabled={!!busy || !loaded}>
            {busy === 'save' ? '저장 중…' : '임시저장'}
          </button>
          <button type="button" className="m-btn m-btn--navy" onClick={async () => { await save(); setNextOpen(true); }} disabled={!!busy || !loaded}>
            다음 · 공고 양식 선택 ›
          </button>
        </div>
      </div>

      <Sheet open={nextOpen} onClose={() => setNextOpen(false)} title="공고 양식 선택은 PC에서 이어서">
        <p className="m-sheet__text">
          공고 양식 업로드 · 초안 평가 · 수정 · 재평가는 화면이 넓은 PC에서 이어서 진행해 주세요.
          지금까지 입력한 내용은 저장했고, PC에서 사업계획서를 열면 그대로 이어집니다.
        </p>
        <button type="button" className="m-btn m-btn--primary" onClick={() => setNextOpen(false)}>확인</button>
      </Sheet>
    </div>
  );
}
