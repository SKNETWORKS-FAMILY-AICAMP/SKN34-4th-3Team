import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api.js';
import { INDUSTRIES, REGIONS } from '../constants.js';
import { linkBtn } from '../utils.js';
import { GovDetailModal, PolicySummaryCard } from './AnnouncementAnalyzer.jsx';
import { paginateSupplementFields, reassessSupplementFields, templateContext } from '../businessPlanSupplement.js';

const BASIC_FIELDS = [
  { key: 'businessName', label: '사업/아이템명', placeholder: '예: 소상공인 재고관리 서비스' },
  { key: 'startupStatus', label: '창업 상태', options: ['예비창업자', '개인사업자', '법인사업자'] },
  { key: 'industry', label: '업종', options: INDUSTRIES },
  { key: 'businessRegion', label: '사업 지역', options: ['전국', ...REGIONS] },
  { key: 'businessType', label: '사업 형태', options: ['1인 창업', '공동 창업', '온라인 서비스', '오프라인 매장', '온·오프라인 병행', '제품 제조·판매'] },
  { key: 'team', label: '팀 구성', placeholder: '구성원과 담당 역할을 입력해 주세요.', multiline: true },
];

const IDEA_FIELDS = [
  { key: 'targetCustomer', label: '목표 고객', placeholder: '누구를 위한 사업인가요?' },
  { key: 'problem', label: '핵심 문제', placeholder: '그 고객이 겪는 문제는 무엇인가요?' },
  { key: 'solution', label: '해결 방안', placeholder: '그 문제를 어떻게 해결하나요?' },
  { key: 'coreFeatures', label: '핵심 기능', placeholder: '제품·서비스가 제공하는 핵심 기능을 입력해 주세요.' },
  { key: 'differentiator', label: '차별점', placeholder: '기존 제품·서비스와 다른 점은 무엇인가요?' },
  { key: 'revenueModel', label: '수익 방식', placeholder: '예: 월 구독료, 판매 수수료, 제품 판매' },
  { key: 'extraNotes', label: '추가 설명 (선택)', placeholder: '초안에 추가로 반영할 내용을 입력해 주세요.', optional: true },
];

const EMPTY_FORM = {
  businessName: '', startupStatus: '', industry: '', businessRegion: '', businessType: '',
  team: '', targetCustomer: '', problem: '', solution: '', coreFeatures: '',
  differentiator: '', revenueModel: '', extraNotes: '', targetProgram: '', templateText: '', tagline: '',
};

const DEV_TEST_PRESET = {
  businessName: '소상공인 재고 관리 서비스',
  startupStatus: '예비창업자',
  industry: '소프트웨어',
  businessRegion: '서울',
  businessType: '1인 창업',
  team: '대표 신대호',
  targetCustomer: '재고 관리가 어렵고 다른 일도 많아서 재고에 계속 신경쓰기 힘든 소상공인',
  problem: '소상공인은 재고 관리 경험이나 노하우가 부족한 경우도 있고 매장 운영하면서 다른 일도 같이 해야해서 재고를 계속 확인하기 어렵다. 그러다보면 필요한 물건이 없거나 반대로 재고가 너무 많이 남아서 비용이 발생할 수 있다.',
  solution: '재고가 부족하거나 너무 오래 남아있는걸 소재관에서 확인하고 알려줘서 사장님이 직접 계속 재고를 확인하지 않아도 되게 하고싶다.',
  coreFeatures: `자동 주문
자주 소진되는 물품은 재고가 일정 수준 이하로 떨어지면 자동으로 주문해서 재고가 부족해지는걸 막는다.

재고 소진 알림
특정 물품이 오랫동안 판매되지 않고 재고로 남아있으면 알림을 보내준다. 필요하면 할인이나 재고를 줄일 수 있는 방법도 같이 알려준다.

재고 현황 확인
현재 어떤 물품이 얼마나 남아있는지 한눈에 볼 수 있게 한다.`,
  differentiator: '단순히 재고 수량만 보여주는게 아니라 재고가 부족하면 주문까지 하고 오래 남아있는 재고도 알려줘서 재고 관리 자체를 편하게 해주는 서비스다.',
  revenueModel: '처음에는 저렴한 구독료로 사용자를 많이 모으고 싶다. 이후에는 소재관에서 상품을 주문할때 발생하는 수수료를 메인 수익으로 가져가는 방식으로 생각하고 있다.',
  extraNotes: '처음에는 재고 관리가 특히 어려운 소규모 매장부터 시작하고 싶다. 기능이 너무 복잡하면 오히려 사용하기 어려울거 같아서 필요한 기능 위주로 단순하게 만들고 싶다.',
};

const STARTUP_STATUS_BY_PROFILE_TYPE = {
  예비: '예비창업자',
  예비창업자: '예비창업자',
  개인: '개인사업자',
  개인사업자: '개인사업자',
  법인: '법인사업자',
  법인사업자: '법인사업자',
};

const LEGACY_DEFAULT_KEYS = new Set(['problem', 'solution', 'scaleUp', 'team']);

function isLegacyDefaultPlan(plan) {
  return Array.isArray(plan?.sections)
    && plan.sections.length === LEGACY_DEFAULT_KEYS.size
    && plan.sections.every((section) => LEGACY_DEFAULT_KEYS.has(section.key));
}

const VISIBLE_STEPS = [
  { key: 'refine', label: '계획 정리' },
  { key: 'setup', label: '공고 양식 선택' },
  { key: 'supplement', label: '계획 보완' },
  { key: 'preview', label: '초안 평가' },
  { key: 'improve', label: '초안 수정' },
  { key: 'done', label: '재평가 및 저장' },
];

const FIELD_ANALYSIS_MARKER = '__FIELD_ANALYSIS_V1__';

function fieldLabel(label) {
  return label.replace(/\s*\[(?:표|행|작성 안내|유형|최대 행|글머리표):[^\]]+\]/g, '').trim();
}

function tableColumns(label) {
  return label.match(/\[표: ([^\]]+)\]/)?.[1].split('|').map((value) => value.trim()) || [];
}

function tableRows(section) {
  const columns = tableColumns(section.label);
  const fixed = section.label.match(/\[행: ([^\]]+)\]/)?.[1].split(',').map((value) => value.trim()) || [];
  let parsed = [];
  if (section.content.trim().startsWith('{')) {
    try {
      const data = JSON.parse(section.content);
      parsed = (data.rows || []).map((row) => columns.map((column) => String(row[column] ?? '')));
    } catch { parsed = []; }
  } else {
    parsed = section.content.split('\n').map((line) =>
      line.replace(/^\||\|$/g, '').split('|').map((value) => value.trim()))
      .filter((row) => row.length === columns.length && row.join('|') !== columns.join('|'));
  }
  if (fixed.length) return fixed.map((label) => parsed.find((row) => row[0] === label)
    || [label, ...columns.slice(1).map(() => '')]);
  return parsed.length ? parsed : [columns.map(() => '')];
}

function serializeTableRows(rows, columns, fixedRows) {
  return JSON.stringify({ rows: rows.filter((row) => row.some((cell, index) =>
    fixedRows ? index > 0 && cell : cell)).map((row) =>
    Object.fromEntries(columns.map((column, index) => [column, row[index]?.trim() || null]))) });
}

function TableSection({ section, onChange }) {
  const columns = tableColumns(section.label);
  const rows = tableRows(section);
  const fixedRows = !!section.label.includes('[행:');
  const maxRows = Number(section.label.match(/\[최대 행: (\d+)\]/)?.[1]) || 10;
  const update = (rowIndex, columnIndex, value) => {
    const next = rows.map((row) => [...row]);
    next[rowIndex][columnIndex] = value.replaceAll('|', '');
    onChange(serializeTableRows(next, columns, fixedRows));
  };
  return (
    <div className="bp-table-wrap">
      <table className="bp-table">
        <thead><tr>{columns.map((column, index) => <th key={`${column}-${index}`}>{column}</th>)}</tr></thead>
        <tbody>{rows.map((row, rowIndex) => (
          <tr key={rowIndex}>{columns.map((column, columnIndex) => (
            <td key={`${column}-${columnIndex}`}>
              {onChange && !(fixedRows && columnIndex === 0) ? (
                <input type="text" value={row[columnIndex] || ''}
                  aria-label={`${fieldLabel(section.label)} ${rowIndex + 1}행 ${column}`}
                  onChange={(event) => update(rowIndex, columnIndex, event.target.value)} />
              ) : row[columnIndex] || ''}
            </td>
          ))}</tr>
        ))}</tbody>
      </table>
      {onChange && !fixedRows && rows.length < maxRows && (
        <button type="button" className="bp-table__add"
          onClick={() => onChange(JSON.stringify({ rows: [...rows, columns.map(() => '')]
            .map((row) => Object.fromEntries(columns.map((column, index) => [column, row[index] || null]))) }))}>
          + 행 추가
        </button>
      )}
    </div>
  );
}

function reviewRows(value, minimum = 1) {
  const lines = String(value || '').split('\n');
  const wrappedLines = lines.reduce((count, line) => count + Math.max(1, Math.ceil(line.length / 42)), 0);
  return Math.min(8, Math.max(minimum, wrappedLines));
}

function FieldControl({ field, value, onChange }) {
  if (field.options) {
    return (
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="" disabled>선택해 주세요</option>
        {value && !field.options.includes(value) && (
          <option value={value} disabled>기존 입력: {value} (다시 선택해 주세요)</option>
        )}
        {field.options.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    );
  }
  if (field.multiline || IDEA_FIELDS.includes(field)) {
    return (
      <textarea rows={reviewRows(value, IDEA_FIELDS.includes(field) && !field.optional ? 5 : 1)}
        value={value} placeholder={field.placeholder}
        onChange={(event) => onChange(event.target.value)} />
    );
  }
  return (
    <input type="text" value={value} placeholder={field.placeholder}
      onChange={(event) => onChange(event.target.value)} />
  );
}

// 임시저장은 서버(bizplan_drafts)가 원본이다. 예전에 이 브라우저에 남긴 초안은
// 서버가 비어 있을 때 한 번 옮기고 지운다. 아래 두 함수는 그 이관에만 쓴다.
const DRAFT_KEY = (userId) => `changeup:bizplan-draft:${userId}`;

function loadLegacyDraft(userId) {
  try {
    const raw = JSON.parse(localStorage.getItem(DRAFT_KEY(userId)) || 'null');
    return raw && typeof raw === 'object' ? raw : null;
  } catch (e) {
    return null;
  }
}
function clearLegacyDraft(userId) {
  try {
    localStorage.removeItem(DRAFT_KEY(userId));
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
  const basicSummary = [form.startupStatus, form.industry, form.businessRegion, form.businessType]
    .filter(Boolean).join(' · ');
  const lines = [
    `# ${form.businessName || '사업계획서'} 초안`,
    '',
    basicSummary ? `> ${basicSummary}` : '',
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

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',', 2)[1] || '');
    reader.onerror = () => reject(reader.error || new Error('파일을 읽지 못했습니다.'));
    reader.readAsDataURL(file);
  });
}

function downloadBase64File({ fileName, mimeType, contentBase64 }) {
  const binary = atob(contentBase64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  const url = URL.createObjectURL(new Blob([bytes], { type: mimeType }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
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

function AnnouncementCards({ items, savedIds, selectedPolicyId, savingId, selectingId, onChoose, onToggleSave, onShowDetail }) {
  return (
    <ul className="bp-announcement-picker__list az2__reclist">
      {items.map((policy) => {
        const saved = savedIds.has(Number(policy.policyId));
        return (
          <PolicySummaryCard key={policy.policyId} item={policy}>
            <button type="button" className="az2__action" onClick={() => onShowDetail(policy)}>요약 보기</button>
            <button type="button" className="az2__action" disabled={selectingId === policy.policyId}
              onClick={() => onChoose(policy)}>
              {selectingId === policy.policyId ? '확인 중…' : Number(selectedPolicyId) === Number(policy.policyId) ? '선택됨' : '이 공고 선택'}
            </button>
            <button type="button" className={'az2__action az2__save' + (saved ? ' is-saved' : '')}
              disabled={savingId === policy.policyId} aria-pressed={saved}
              onClick={() => onToggleSave(policy)}>
              {savingId === policy.policyId ? '처리 중…' : saved ? '★ 저장됨' : '☆ 저장'}
            </button>
          </PolicySummaryCard>
        );
      })}
    </ul>
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

export function BusinessPlanPage({ user, onRequireLogin, savedPolicies = [], onToggleSavedPolicy }) {
  const userId = user && user.id;
  const mainRef = useRef(null);
  const [active, setActive] = useState('refine');
  const [form, setForm] = useState(EMPTY_FORM);
  const [profileIndustry, setProfileIndustry] = useState('');
  const editedFieldsRef = useRef(new Set());
  const [plan, setPlan] = useState(null); // { sections: [{key,label,content}], summary, llmUsed }
  const [evalResult, setEvalResult] = useState(null);
  const [revisionSections, setRevisionSections] = useState([]);
  const [finalPlan, setFinalPlan] = useState(null);
  const [finalEvalResult, setFinalEvalResult] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [finalEvaluating, setFinalEvaluating] = useState(false);
  const [err, setErr] = useState('');
  const [savedNote, setSavedNote] = useState('');
  const [announcements, setAnnouncements] = useState([]);
  const [announcementError, setAnnouncementError] = useState('');
  const [selectedAnnouncementId, setSelectedAnnouncementId] = useState('');
  const [selectedAnnouncementInfo, setSelectedAnnouncementInfo] = useState(null);
  const [announcementPickerOpen, setAnnouncementPickerOpen] = useState(false);
  const [pickerQuery, setPickerQuery] = useState('');
  const [pickerPolicies, setPickerPolicies] = useState([]);
  const [pickerPage, setPickerPage] = useState(1);
  const [pickerHasMore, setPickerHasMore] = useState(false);
  const [pickerLoading, setPickerLoading] = useState(false);
  const [pickerError, setPickerError] = useState('');
  const [detailPolicy, setDetailPolicy] = useState(null);
  const pickerQueryRef = useRef('');
  const pickerLoadingMoreRef = useRef(false);
  const [savingPolicyId, setSavingPolicyId] = useState(null);
  const [selectingPolicyId, setSelectingPolicyId] = useState(null);
  const [pickerSaveError, setPickerSaveError] = useState('');
  const [templateFile, setTemplateFile] = useState(null);
  const [templateError, setTemplateError] = useState('');
  const [templateInfo, setTemplateInfo] = useState(null);
  const [inspectingTemplate, setInspectingTemplate] = useState(false);
  const [analyzingFields, setAnalyzingFields] = useState(false);
  const [fieldAnalysis, setFieldAnalysis] = useState([]);
  const [supplementAnswers, setSupplementAnswers] = useState({});
  const [supplementImages, setSupplementImages] = useState({});
  const [supplementChoices, setSupplementChoices] = useState({});
  const [supplementPage, setSupplementPage] = useState(0);
  const [editedSectionKeys, setEditedSectionKeys] = useState([]);
  const [refining, setRefining] = useState(false);
  const [refinedDone, setRefinedDone] = useState(false);
  const [renderingFormat, setRenderingFormat] = useState('');

  // 서버에서 받은 초안을 화면 상태로 되돌린다. 불러오는 동안 사용자가 고친 기초 정보는 유지한다.
  const applyDraft = (draft) => {
    setForm((previous) => {
      const next = { ...EMPTY_FORM, ...(draft.form || {}) };
      editedFieldsRef.current.forEach((key) => { next[key] = previous[key]; });
      return next;
    });
    if (draft.plan && Array.isArray(draft.plan.sections) && !isLegacyDefaultPlan(draft.plan)) {
      setPlan(draft.plan);
      if (draft.evalResult) setEvalResult(draft.evalResult);
      setRevisionSections(draft.revisionSections || draft.plan.sections);
      if (draft.finalPlan) setFinalPlan(draft.finalPlan);
      if (draft.finalEvalResult) setFinalEvalResult(draft.finalEvalResult);
    }
    if (draft.selectedAnnouncementId) setSelectedAnnouncementId(String(draft.selectedAnnouncementId));
    if (draft.selectedAnnouncementInfo) setSelectedAnnouncementInfo(draft.selectedAnnouncementInfo);
    if (draft.refinedDone) setRefinedDone(true);
    if (Array.isArray(draft.fieldAnalysis)) setFieldAnalysis(draft.fieldAnalysis);
    if (draft.supplementAnswers) setSupplementAnswers(draft.supplementAnswers);
    if (draft.supplementImages) setSupplementImages(draft.supplementImages);
    if (draft.templateInfo) {
      setTemplateInfo(draft.templateInfo);
      setTemplateFile({ name: draft.templateInfo.fileName });
    }
    if (draft.supplementChoices) setSupplementChoices(draft.supplementChoices);
    if (Number.isInteger(draft.supplementPage)) setSupplementPage(draft.supplementPage);
    if (Array.isArray(draft.editedSectionKeys)) setEditedSectionKeys(draft.editedSectionKeys);
  };

  // 임시저장한 값은 복원하고, 비어 있는 기초 정보만 가입 프로필로 채운다.
  useEffect(() => {
    if (!userId) return;
    editedFieldsRef.current = new Set();
    setProfileIndustry('');
    setForm({ ...EMPTY_FORM });
    let current = true;
    Promise.allSettled([api.bizplanDraft(), api.me(), api.businessProfile()])
      .then(([draftResult, meResult, profileResult]) => {
        if (!current) return;
        const serverDraft = draftResult.status === 'fulfilled' ? draftResult.value?.data : null;
        // 서버에 초안이 없을 때만 이 브라우저의 예전 초안을 옮긴다. 조회 실패 시에는 덮어쓰지 않게 건너뛴다.
        const legacyDraft = draftResult.status === 'fulfilled' && !serverDraft ? loadLegacyDraft(userId) : null;
        const draft = serverDraft || legacyDraft;
        if (draft) applyDraft(draft);
        if (legacyDraft) {
          api.saveBizplanDraft(legacyDraft)
            .then(() => clearLegacyDraft(userId))
            .catch(() => { /* 다음 방문 때 다시 시도 */ });
        }
        const me = meResult.status === 'fulfilled' ? meResult.value : null;
        const profile = profileResult.status === 'fulfilled' ? profileResult.value : null;
        const industry = profile?.industry?.trim() || '';
        setProfileIndustry(industry);
        const initialValues = {
          businessRegion: REGIONS.includes(me?.region) ? me.region : '',
          industry,
          startupStatus: STARTUP_STATUS_BY_PROFILE_TYPE[profile?.businessType] || '',
        };
        setForm((previous) => {
          const next = { ...previous };
          Object.entries(initialValues).forEach(([key, value]) => {
            if (value && !next[key] && !editedFieldsRef.current.has(key)) next[key] = value;
          });
          return next;
        });
      });
    return () => { current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  useEffect(() => {
    if (mainRef.current) mainRef.current.scrollTop = 0;
  }, [active, supplementPage]);

  useEffect(() => {
    if (!userId) return;
    let current = true;
    api.announcements({ limit: 100 }).then((result) => {
      if (current) setAnnouncements(result.announcements || []);
    }).catch(() => {
      if (current) setAnnouncementError('공고 목록을 불러오지 못했습니다. 잠시 후 다시 열어 주세요.');
    });
    return () => { current = false; };
  }, [userId]);

  useEffect(() => {
    if (!announcementPickerOpen) return undefined;
    const onKeyDown = (event) => {
      if (event.key === 'Escape' && !detailPolicy) setAnnouncementPickerOpen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [announcementPickerOpen, detailPolicy]);

  useEffect(() => {
    if (!announcementPickerOpen) return undefined;
    const keyword = pickerQuery.trim();
    pickerQueryRef.current = keyword;
    setPickerPolicies([]);
    setPickerPage(1);
    setPickerHasMore(false);
    setPickerLoading(true);
    setPickerError('');
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      api.policies({ keyword: keyword || undefined, page: 1, size: 30, only_announcements: true }, { signal: controller.signal }).then((result) => {
        const policies = result.policies || [];
        setPickerPolicies(policies);
        setPickerHasMore(policies.length === 30);
      }).catch((error) => {
        if (error?.name !== 'AbortError') setPickerError('공고 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.');
      }).finally(() => {
        if (!controller.signal.aborted) setPickerLoading(false);
      });
    }, keyword ? 250 : 0);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
      pickerQueryRef.current = '';
    };
  }, [announcementPickerOpen, pickerQuery]);

  const loadMorePickerPolicies = async () => {
    if (pickerLoading || !pickerHasMore || pickerLoadingMoreRef.current) return;
    pickerLoadingMoreRef.current = true;
    const keyword = pickerQuery.trim();
    const nextPage = pickerPage + 1;
    setPickerLoading(true);
    setPickerError('');
    try {
      const result = await api.policies({ keyword: keyword || undefined, page: nextPage, size: 30, only_announcements: true });
      if (pickerQueryRef.current !== keyword) return;
      const policies = result.policies || [];
      setPickerPolicies((current) => [...current, ...policies]);
      setPickerPage(nextPage);
      setPickerHasMore(policies.length === 30);
    } catch {
      if (pickerQueryRef.current === keyword) setPickerError('공고를 더 불러오지 못했습니다. 다시 시도해 주세요.');
    } finally {
      pickerLoadingMoreRef.current = false;
      if (pickerQueryRef.current === keyword) setPickerLoading(false);
    }
  };

  const setReviewedField = (key, value) => {
    editedFieldsRef.current.add(key);
    setForm((f) => ({ ...f, [key]: value }));
    setPlan(null);
    setEvalResult(null);
    setRevisionSections([]);
    setFinalPlan(null);
    setFinalEvalResult(null);
    setFieldAnalysis([]);
    setSupplementAnswers({});
    setSupplementImages({});
    setSupplementChoices({});
    setSupplementPage(0);
  };
  const applyTestPreset = () => {
    Object.keys(DEV_TEST_PRESET).forEach((key) => editedFieldsRef.current.add(key));
    setForm((current) => ({ ...current, ...DEV_TEST_PRESET }));
    setRefinedDone(false);
    setPlan(null);
    setEvalResult(null);
    setRevisionSections([]);
    setFinalPlan(null);
    setFinalEvalResult(null);
    setFieldAnalysis([]);
    setSupplementAnswers({});
    setSupplementImages({});
    setSupplementChoices({});
    setSupplementPage(0);
    setEditedSectionKeys([]);
    setErr('');
    setActive('refine');
  };
  const onSectionChange = (key, content) => {
    setEditedSectionKeys((keys) => keys.includes(key) ? keys : [...keys, key]);
    setRevisionSections((sections) => sections.map((section) =>
      section.key === key ? { ...section, content } : section));
    setFinalPlan(null);
    setFinalEvalResult(null);
  };

  const industryOptions = [
    ...(import.meta.env.DEV ? ['소프트웨어'] : []),
    ...(profileIndustry && !INDUSTRIES.includes(profileIndustry)
      && !(import.meta.env.DEV && profileIndustry === '소프트웨어')
      ? [profileIndustry] : []),
    ...INDUSTRIES,
  ];
  const basicReady = BASIC_FIELDS.every((field) => form[field.key].trim()
    && (!field.options || (field.key === 'industry' ? industryOptions : field.options).includes(form[field.key])));
  const ideaReady = IDEA_FIELDS.filter((field) => !field.optional)
    .every((field) => form[field.key].trim());
  const selectedAnnouncement = selectedAnnouncementInfo
    || announcements.find((item) => String(item.id) === selectedAnnouncementId);
  const savedPolicyIds = new Set(savedPolicies.map((item) => Number(item.policyId)));
  const policyMatchesQuery = (item) => {
    const keyword = pickerQuery.trim().toLocaleLowerCase();
    return !keyword || [item.title, item.source, item.region, item.industry, item.target, item.benefit]
      .some((value) => String(value || '').toLocaleLowerCase().includes(keyword));
  };
  const savedPickerItems = savedPolicies.filter((policy) => policy.announcementId && policyMatchesQuery(policy));
  const relatedPickerItems = pickerPolicies.filter((policy) => !savedPolicyIds.has(Number(policy.policyId)));

  const openAnnouncementPicker = () => {
    setPickerQuery('');
    setPickerSaveError('');
    setAnnouncementPickerOpen(true);
  };
  const chooseAnnouncement = async (policy) => {
    if (Number(selectedAnnouncement?.policyId) === Number(policy.policyId)) {
      setAnnouncementPickerOpen(false);
      return;
    }
    setSelectingPolicyId(policy.policyId);
    setPickerSaveError('');
    try {
      const detail = await api.policy(policy.policyId);
      if (!detail.announcementId) {
        setPickerSaveError('이 공고의 원문 정보를 찾을 수 없습니다. 다른 공고를 선택해 주세요.');
        return;
      }
      const info = { id: String(detail.announcementId), policyId: policy.policyId, title: policy.title };
      setSelectedAnnouncementId(info.id);
      setSelectedAnnouncementInfo(info);
      setReviewedField('targetProgram', info.title || '');
      setAnnouncementPickerOpen(false);
    } catch {
      setPickerSaveError('공고 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.');
    } finally {
      setSelectingPolicyId(null);
    }
  };
  const clearAnnouncement = () => {
    if (!selectedAnnouncement) return;
    setSelectedAnnouncementId('');
    setSelectedAnnouncementInfo(null);
    setReviewedField('targetProgram', '');
  };
  const togglePickerSave = async (policy) => {
    if (!onToggleSavedPolicy) return;
    setPickerSaveError('');
    setSavingPolicyId(policy.policyId);
    try {
      await onToggleSavedPolicy(policy);
    } catch {
      setPickerSaveError('공고 저장 상태를 변경하지 못했습니다. 다시 시도해 주세요.');
    } finally {
      setSavingPolicyId(null);
    }
  };

  const stepDone = (key) => {
    if (key === 'refine') return refinedDone && basicReady && ideaReady;
    if (key === 'setup') return !!plan;
    if (key === 'supplement') return !!plan && (!templateInfo || !!fieldAnalysis.length);
    if (key === 'preview') return !!evalResult;
    if (key === 'improve') return !!finalPlan;
    if (key === 'done') return !!finalEvalResult;
    return false;
  };

  const runRefine = async () => {
    if (!basicReady || !ideaReady || refining) return;
    setErr('');
    setRefining(true);
    try {
      const res = await api.refineBusinessPlan({ input: {
        businessName: form.businessName,
        startupStatus: form.startupStatus,
        industry: form.industry,
        businessRegion: form.businessRegion,
        businessType: form.businessType,
        team: form.team,
        targetCustomer: form.targetCustomer,
        problem: form.problem,
        solution: form.solution,
        coreFeatures: form.coreFeatures,
        differentiator: form.differentiator,
        revenueModel: form.revenueModel,
        extraNotes: form.extraNotes,
      } });
      setForm((current) => ({
        ...current,
        ...res.refined,
        ...Object.fromEntries(BASIC_FIELDS.filter((field) => field.options)
          .map((field) => [field.key, current[field.key]])),
      }));
      setPlan(null);
      setEvalResult(null);
      setRevisionSections([]);
      setFinalPlan(null);
      setFinalEvalResult(null);
      setFieldAnalysis([]);
      setSupplementAnswers({});
      setSupplementImages({});
      setSupplementChoices({});
      setSupplementPage(0);
      setEditedSectionKeys([]);
      setRefinedDone(true);
    } catch (e2) {
      if (e2 && e2.status === 401) onRequireLogin && onRequireLogin();
      else setErr(e2.detail || '입력 내용을 정리하지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setRefining(false);
    }
  };

  const inspectTemplate = async (event) => {
    const input = event.target;
    const file = input.files?.[0] || null;
    setPlan(null);
    setEvalResult(null);
    setRevisionSections([]);
    setFinalPlan(null);
    setFinalEvalResult(null);
    setTemplateInfo(null);
    setFieldAnalysis([]);
    setSupplementAnswers({});
    setSupplementImages({});
    setSupplementChoices({});
    setSupplementPage(0);
    setEditedSectionKeys([]);
    if (!file) {
      setTemplateFile(null);
      setTemplateError('');
      return;
    }
    if (!/\.(pdf|hwpx)$/i.test(file.name) || file.size > 4 * 1024 * 1024) {
      setTemplateError('PDF 또는 HWPX 파일을 4 MiB 이하로 선택해 주세요.');
      setTemplateFile(null);
      input.value = '';
      return;
    }
    setTemplateFile(file);
    setTemplateError('');
    setInspectingTemplate(true);
    try {
      const contentBase64 = await fileToBase64(file);
      const inspected = await api.inspectBusinessPlanTemplate({ fileName: file.name, contentBase64 });
      setTemplateInfo({ ...inspected, fileName: file.name, contentBase64 });
    } catch (e2) {
      if (e2 && e2.status === 401) onRequireLogin && onRequireLogin();
      setTemplateError(e2.detail || '양식의 입력 위치를 확인하지 못했습니다. 다른 파일을 선택해 주세요.');
      setTemplateFile(null);
      input.value = '';
    } finally {
      setInspectingTemplate(false);
    }
  };

  const evaluateSections = (sections) => api.evaluateBusinessPlan({
    sections,
    announcementId: selectedAnnouncement ? Number(selectedAnnouncementId) : null,
    templateFields: templateInfo?.fields || [],
  });

  const generatePlan = async (analysis = fieldAnalysis) => {
    if (!userId) {
      onRequireLogin && onRequireLogin();
      return;
    }
    if (!basicReady) {
      setActive('refine');
      setErr('계획 정리의 기초 정보 항목을 모두 입력해 주세요.');
      return;
    }
    if (!ideaReady) {
      setActive('refine');
      setErr('계획 정리의 아이디어 항목을 모두 입력해 주세요.');
      return;
    }
    if (!refinedDone) {
      setActive('refine');
      setErr('계획 정리에서 AI로 입력 내용을 정리한 뒤 결과를 검토해 주세요.');
      return;
    }
    if (templateFile && !templateInfo) {
      setActive('setup');
      setErr('양식 분석이 완료될 때까지 기다려 주세요.');
      return;
    }
    if (templateInfo && !analysis.length) {
      setActive('setup');
      setErr('먼저 양식의 입력 영역을 분석해 주세요.');
      return;
    }
    const context = templateInfo ? templateContext(analysis, supplementAnswers, supplementChoices) : '';
    if (context.length > 12000) {
      setErr('추가 정보가 너무 깁니다. 답변을 조금 줄여 주세요.');
      return;
    }
    setErr('');
    setGenerating(true);
    try {
      const res = await api.generateBusinessPlan({
        ...form,
        targetProgram: selectedAnnouncement?.title || '',
        templateText: context,
        announcementId: selectedAnnouncement ? Number(selectedAnnouncementId) : null,
        templateFields: templateInfo?.fields || [],
      });
      setPlan(res);
      setActive('preview');
      setEvalResult(null);
      setRevisionSections(res.sections);
      setEditedSectionKeys([]);
      setFinalPlan(null);
      setFinalEvalResult(null);
      setGenerating(false);
      setEvaluating(true);
      try {
        const score = await evaluateSections(res.sections);
        setEvalResult(score);
      } catch (_) {
        setErr('초안은 작성됐지만 평가를 받지 못했습니다. 초안 평가에서 다시 시도해 주세요.');
      } finally {
        setEvaluating(false);
      }
    } catch (e2) {
      if (e2 && e2.status === 401) onRequireLogin && onRequireLogin();
      else setErr('초안을 만들지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setGenerating(false);
    }
  };

  const runTemplateAnalysis = async () => {
    if (!templateInfo || analyzingFields || generating) return;
    if (!basicReady || !ideaReady || !refinedDone) {
      setActive('refine');
      setErr('계획 정리의 입력 내용을 먼저 완료해 주세요.');
      return;
    }
    setErr('');
    setPlan(null);
    setEvalResult(null);
    setFinalPlan(null);
    setFinalEvalResult(null);
    setAnalyzingFields(true);
    try {
      const result = await api.generateBusinessPlan({
        ...form,
        targetProgram: selectedAnnouncement?.title || '',
        announcementId: selectedAnnouncement ? Number(selectedAnnouncementId) : null,
        templateFields: templateInfo.fields,
        templateText: FIELD_ANALYSIS_MARKER,
      });
      const fields = result.sections.map((section) => ({
        ...JSON.parse(section.content),
        label: section.label,
      }));
      if (fields.length !== templateInfo.fields.length) throw new Error('field count mismatch');
      setFieldAnalysis(fields);
      setSupplementAnswers({});
      setSupplementImages({});
      setSupplementChoices({});
      setSupplementPage(0);
      if (fields.some((field) => field.status === 'partial' || field.status === 'missing'
        || field.status === 'unsupported')) {
        setActive('supplement');
      } else {
        setAnalyzingFields(false);
        await generatePlan(fields);
      }
    } catch (error) {
      if (error && error.status === 401) onRequireLogin && onRequireLogin();
      else setErr(error?.detail || '양식의 입력 영역 분석에 실패했습니다. 다시 시도해 주세요.');
    } finally {
      setAnalyzingFields(false);
    }
  };

  const runEvaluate = async () => {
    if (!plan) return;
    setErr('');
    setEvaluating(true);
    try {
      const res = await evaluateSections(plan.sections);
      setEvalResult(res);
    } catch (e2) {
      if (e2 && e2.status === 401) onRequireLogin && onRequireLogin();
      else setErr('예비진단을 실행하지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setEvaluating(false);
    }
  };

  const attachSupplementImage = async (fieldId, file) => {
    if (!file) return;
    if (!['image/png', 'image/jpeg'].includes(file.type) || file.size > 2 * 1024 * 1024) {
      setErr('이미지는 2 MiB 이하의 PNG 또는 JPEG 파일로 첨부해 주세요.');
      return;
    }
    const otherBytes = Object.entries(supplementImages).reduce((total, [key, image]) =>
      total + (key === fieldId ? 0 : image.size || 0), 0);
    if (otherBytes + file.size > 4 * 1024 * 1024) {
      setErr('첨부 이미지의 합계는 4 MiB 이하여야 합니다.');
      return;
    }
    try {
      const contentBase64 = await fileToBase64(file);
      setSupplementImages((current) => ({ ...current, [fieldId]: {
        fileName: file.name, mimeType: file.type, contentBase64, size: file.size,
      } }));
      setSupplementChoices((current) => ({ ...current, [fieldId]: 'answer' }));
      setErr('');
    } catch {
      setErr('이미지 파일을 읽지 못했습니다. 다시 선택해 주세요.');
    }
  };

  const completeSupplement = () => {
    const updated = reassessSupplementFields(fieldAnalysis, supplementAnswers, supplementChoices, supplementImages);
    setFieldAnalysis(updated);
    setSupplementPage(0);
    generatePlan(updated);
  };

  const regeneratePlan = async () => {
    if (!plan || !evalResult || generating || !revisionSections.length) return;
    const context = templateInfo
      ? templateContext(fieldAnalysis, supplementAnswers, supplementChoices, editedSectionKeys)
      : '__USER_EDITS_V1__\n' + JSON.stringify(editedSectionKeys);
    if (context.length > 12000) {
      setErr('보완 정보가 너무 깁니다. 내용을 조금 줄여 주세요.');
      return;
    }
    setErr('');
    setGenerating(true);
    try {
      const res = await api.generateBusinessPlan({
        ...form,
        targetProgram: selectedAnnouncement?.title || '',
        templateText: context,
        announcementId: selectedAnnouncement ? Number(selectedAnnouncementId) : null,
        templateFields: templateInfo?.fields || [],
        reviewedSections: revisionSections,
      });
      setFinalPlan(res);
      setFinalEvalResult(null);
      setGenerating(false);
      setActive('done');
      setFinalEvaluating(true);
      try {
        setFinalEvalResult(await evaluateSections(res.sections));
      } catch (e2) {
        if (e2 && e2.status === 401) onRequireLogin && onRequireLogin();
        else setErr('보완 초안은 작성됐지만 재평가에 실패했습니다. 다시 시도해 주세요.');
      } finally {
        setFinalEvaluating(false);
      }
    } catch (e2) {
      if (e2 && e2.status === 401) onRequireLogin && onRequireLogin();
      else setErr(e2.detail || '보완 초안을 만들지 못했습니다. 잠시 후 다시 시도해 주세요.');
    } finally {
      setGenerating(false);
    }
  };

  const runFinalEvaluate = async () => {
    if (!finalPlan || finalEvaluating) return;
    setErr('');
    setFinalEvaluating(true);
    try {
      setFinalEvalResult(await evaluateSections(finalPlan.sections));
    } catch (e2) {
      if (e2 && e2.status === 401) onRequireLogin && onRequireLogin();
      else setErr('보완 초안을 재평가하지 못했습니다. 잠시 후 다시 시도해 주세요.');
    } finally {
      setFinalEvaluating(false);
    }
  };

  const renderPlan = async (format) => {
    if (!finalPlan || renderingFormat) return;
    setErr('');
    setRenderingFormat(format);
    try {
      const rendered = await api.renderBusinessPlan({
        format,
        title: form.businessName || '사업계획서',
        sections: finalPlan.sections,
        template: templateInfo ? {
          fileName: templateInfo.fileName,
          contentBase64: templateInfo.contentBase64,
        } : null,
        images: finalPlan.sections.filter((section) =>
          supplementImages[section.key] && supplementChoices[section.key] !== 'not_applicable'
          && supplementChoices[section.key] !== 'no_information').map((section) => ({
          key: section.key,
          mimeType: supplementImages[section.key].mimeType,
          contentBase64: supplementImages[section.key].contentBase64,
        })),
      });
      downloadBase64File(rendered);
    } catch (e2) {
      if (e2 && e2.status === 401) onRequireLogin && onRequireLogin();
      else setErr(e2.detail || `${format.toUpperCase()} 파일을 만들지 못했습니다. 잠시 후 다시 시도해 주세요.`);
    } finally {
      setRenderingFormat('');
    }
  };

  const goStep = (key) => {
    setErr('');
    setActive(key);
  };

  const saveNow = async () => {
    if (!userId) {
      onRequireLogin && onRequireLogin();
      return;
    }
    let note = '임시저장했어요';
    try {
      await api.saveBizplanDraft({
        form, plan, evalResult, revisionSections, finalPlan, finalEvalResult,
        selectedAnnouncementId, selectedAnnouncementInfo, refinedDone, templateInfo,
        fieldAnalysis, supplementAnswers, supplementImages, supplementChoices, supplementPage, editedSectionKeys,
      });
    } catch (e2) {
      if (e2 && e2.status === 401) {
        onRequireLogin && onRequireLogin();
        return;
      }
      note = e2 && e2.status === 413
        ? '첨부 파일이 너무 커서 임시저장하지 못했습니다.'
        : '임시저장하지 못했습니다. 잠시 후 다시 시도해 주세요.';
    }
    setSavedNote(note);
    setTimeout(() => setSavedNote(''), 2000);
  };

  const needsSupplement = fieldAnalysis.some((field) =>
    field.status === 'partial' || field.status === 'missing' || field.status === 'unsupported'
    || field.type === 'image');
  const supplementItems = fieldAnalysis.filter((field) =>
    ['partial', 'missing', 'unsupported'].includes(field.status) || field.type === 'image');
  const visibleImages = Object.fromEntries(Object.entries(supplementImages).filter(([key]) =>
    !['not_applicable', 'no_information'].includes(supplementChoices[key])));
  const supplementPages = paginateSupplementFields(supplementItems);
  const currentSupplementPage = Math.min(supplementPage, Math.max(0, supplementPages.length - 1));
  const visibleSteps = templateInfo && (!fieldAnalysis.length || needsSupplement)
    ? VISIBLE_STEPS : VISIBLE_STEPS.filter((step) => step.key !== 'supplement');
  const activeIdx = visibleSteps.findIndex((step) => step.key === active);
  const nextStep = visibleSteps[activeIdx + 1];
  const evaluationBasis = selectedAnnouncement
    ? `선택한 공고와 ${templateInfo ? '제출한 양식' : '기본 PSST 양식'}`
    : templateInfo ? '제출한 양식' : '기본 PSST 양식';

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
      <div className="bp2__body">
        <aside className="bp2__sidebar">
          <nav className="bp2__nav" aria-label="사업계획서 작성 단계">
            {visibleSteps.map((step) => (
              <button
                key={step.key}
                type="button"
                className={'bp2__navitem' + (active === step.key ? ' is-active' : '')}
                onClick={() => goStep(step.key)}
              >
                <span className={'bp2__navcheck' + (stepDone(step.key) ? ' is-done' : '')} aria-hidden="true">
                  {stepDone(step.key) ? '✔' : ''}
                </span>
                {step.label}
              </button>
            ))}
          </nav>
          <div className="bp2__actions">
            {savedNote && <span className="bp2__saved" role="status">{savedNote}</span>}
            <button type="button" className="bp2__save" onClick={saveNow}>임시저장</button>
            {nextStep && (
              <button type="button" className="bp2__next" onClick={() => goStep(nextStep.key)}>
                다음 단계 · {nextStep.label} ›
              </button>
            )}
            {import.meta.env.DEV && (
              <button type="button" className="bp2__preset" onClick={applyTestPreset}>
                테스트용 프리셋 적용
              </button>
            )}
          </div>
        </aside>

        <main className="bp2__main" ref={mainRef}>
          {err && <p className="cal__err">{err}</p>}

          {active === 'refine' && (
            <section>
              <h3 className="bp2__stepttl">계획 정리</h3>
              <p className="bp2__stepdesc">기초 정보와 아이디어를 입력한 뒤 AI로 정리하세요. 정리된 내용도 직접 수정할 수 있습니다.</p>
              <p className="bp-hint">{refinedDone ? 'AI 정리가 완료됐습니다. 내용을 검토하고 필요한 부분을 수정해 주세요.' : '추가 설명을 제외한 모든 항목을 입력하면 AI 정리를 시작할 수 있습니다.'}</p>
              <div className="bp-review">
                <div className="bp-review__group">
                  <h4>기초 정보</h4>
                  <div className="bp-review__basics">
                    {BASIC_FIELDS.map((field) => (
                      <label key={field.key} className={'bp-field' + (field.multiline ? ' bp-review__wide' : field.key === 'businessName' ? ' bp-review__name' : '')}>
                        <span className="bp-field__label">{field.label}</span>
                        <FieldControl field={field.key === 'industry' ? { ...field, options: industryOptions } : field}
                          value={form[field.key]}
                          onChange={(value) => setReviewedField(field.key, value)} />
                      </label>
                    ))}
                  </div>
                </div>
                <div className="bp-review__group">
                  <h4>아이디어 정리</h4>
                  <div className="bp-review__ideas">
                    {IDEA_FIELDS.map((field) => (
                      <label key={field.key} className={'bp-field' + (field.optional ? ' bp-review__wide' : '')}>
                        <span className="bp-field__label">{field.label}</span>
                        <FieldControl field={field} value={form[field.key]}
                          onChange={(value) => setReviewedField(field.key, value)} />
                      </label>
                    ))}
                  </div>
                </div>
              </div>
              <button type="button" className="exp-upload" onClick={runRefine} disabled={!basicReady || !ideaReady || refining}>
                {refining ? '입력 정리 중…' : refinedDone ? 'AI로 다시 정리하기' : 'AI로 입력 정리하기'}
              </button>
            </section>
          )}

          {active === 'setup' && (
            <section>
              <h3 className="bp2__stepttl">공고 양식 선택</h3>
              <p className="bp2__stepdesc">공고와 양식은 선택 사항입니다. 양식이 없으면 기본 PSST 양식으로 초안을 만듭니다.</p>
              <div className="bp-field">
                <span className="bp-field__label">제출할 공고 (선택)</span>
                <div className="bp-announcement-choice" role="group" aria-label="공고 선택 방식">
                  <button type="button" className={selectedAnnouncement ? 'is-selected' : ''}
                    aria-pressed={!!selectedAnnouncement} onClick={openAnnouncementPicker}>
                    공고 선택
                  </button>
                  <button type="button" className={!selectedAnnouncement ? 'is-selected' : ''}
                    aria-pressed={!selectedAnnouncement} onClick={clearAnnouncement}>
                    공고 선택 안함
                  </button>
                </div>
                {selectedAnnouncement && (
                  <p className="bp-announcement-choice__selected" role="status">
                    선택한 공고: {selectedAnnouncement.title}
                  </p>
                )}
              </div>
              {announcementError && <p className="cal__err">{announcementError}</p>}
              <label className="bp-field">
                <span className="bp-field__label">사업계획서 양식 (선택 · PDF/HWPX)</span>
                <input type="file" accept=".pdf,.hwpx" onChange={inspectTemplate} disabled={inspectingTemplate} />
              </label>
              {templateError && <p className="cal__err">{templateError}</p>}
              <p className="bp-hint">{templateFile
                ? inspectingTemplate
                  ? `${templateFile.name} 분석 중…`
                  : `${templateFile.name} 분석 완료 · ${templateInfo?.fields?.length || 0}개 작성 항목을 찾았습니다.`
                : '양식을 선택하지 않으면 기본 PSST 항목을 사용합니다.'}</p>
              {!refinedDone && <p className="bp-hint">계획 정리에서 AI 정리를 완료해야 초안을 만들 수 있습니다.</p>}
              <button type="button" className="exp-upload"
                onClick={() => templateInfo ? runTemplateAnalysis() : generatePlan()}
                disabled={inspectingTemplate || analyzingFields || (!!templateFile && !templateInfo)
                  || !basicReady || !ideaReady || !refinedDone || generating}>
                {analyzingFields ? '양식 입력 영역 분석 중…' : generating ? '초안 작성 중…'
                  : templateInfo ? '양식 분석하고 초안 준비하기' : 'AI 초안 만들기'}
              </button>
            </section>
          )}

          {active === 'supplement' && (
            <section>
              <h3 className="bp2__stepttl">계획 보완</h3>
              <p className="bp2__stepdesc">선택한 양식에서 추가 정보가 필요한 입력 칸만 확인하세요. 모르는 정보는 비워 둘 수 있습니다.</p>
              {!fieldAnalysis.length ? (
                <div className="bp2__empty">
                  <p>공고 양식 선택에서 양식을 분석해 주세요.</p>
                  <button type="button" className="exp-upload" onClick={() => goStep('setup')}>← 공고 양식 선택으로 이동</button>
                </div>
              ) : !supplementPages.length ? (
                <div className="bp2__empty">
                  <p>추가로 확인할 정보가 없습니다.</p>
                  <button type="button" className="exp-upload" onClick={() => generatePlan(fieldAnalysis)}
                    disabled={generating}>AI 초안 만들기</button>
                </div>
              ) : (
                <React.Fragment>
                  <p className="bp-supplement__counter" aria-live="polite">
                    {currentSupplementPage + 1} / {supplementPages.length}
                  </p>
                  <div className="bp-supplement__page">
                    {(supplementPages[currentSupplementPage] || []).map((field) => (
                      <div className="bp-supplement" key={field.field_id}>
                        <h4>{fieldLabel(field.label)}</h4>
                        <p>{field.instruction || field.missing_reason}</p>
                        {!!field.mapped_information?.length && (
                          <p className="bp-hint">기존 정보: {field.mapped_information.join(' · ')}</p>
                        )}
                        {field.status === 'unsupported' && field.type !== 'image' ? (
                          <p className="bp-hint">{field.missing_reason || '이 영역은 자동 배치를 보장할 수 없습니다. 원본 양식에서 직접 확인해 주세요.'}</p>
                        ) : (
                          <React.Fragment>
                            {field.type === 'table' && <p className="bp-hint">표의 열: {field.columns?.join(' · ')}</p>}
                            <fieldset className="bp-supplement__choice">
                              <legend>추가 정보 상태</legend>
                              {[
                                ['answer', '정보 입력'],
                                ['no_information', '현재 정보 없음'],
                                ['not_applicable', '해당 사항 없음'],
                              ].map(([value, label]) => (
                                <label key={value}>
                                  <input type="radio" name={`${field.field_id}-choice`}
                                    checked={(supplementChoices[field.field_id] || 'answer') === value}
                                    onChange={() => setSupplementChoices((current) => ({
                                      ...current, [field.field_id]: value,
                                    }))} /> {label}
                                </label>
                              ))}
                            </fieldset>
                            {(supplementChoices[field.field_id] || 'answer') === 'answer' && field.type === 'image' && (
                              <div className="bp-supplement__attachment">
                                <label className="bp-field">
                                  <span className="bp-field__label">이미지 파일 (PNG/JPEG · 2 MiB 이하)</span>
                                  <input type="file" accept="image/png,image/jpeg"
                                    onChange={(event) => {
                                      const file = event.target.files?.[0];
                                      event.target.value = '';
                                      attachSupplementImage(field.field_id, file);
                                    }} />
                                </label>
                                {supplementImages[field.field_id] && (
                                  <div>
                                    <img className="bp-supplement__image" alt={`${fieldLabel(field.label)} 첨부 미리보기`}
                                      src={`data:${supplementImages[field.field_id].mimeType};base64,${supplementImages[field.field_id].contentBase64}`} />
                                    <p className="bp-hint">{supplementImages[field.field_id].fileName}</p>
                                    <button type="button" className="bp-table__add" onClick={() => {
                                      setSupplementImages((current) => {
                                        const next = { ...current };
                                        delete next[field.field_id];
                                        return next;
                                      });
                                    }}>이미지 제거</button>
                                  </div>
                                )}
                              </div>
                            )}
                            {(supplementChoices[field.field_id] || 'answer') === 'answer' && field.type !== 'image' &&
                              (field.missing_fields?.length ? field.missing_fields : field.required_information).map((item) => (
                                <label className="bp-field" key={item}>
                                  <span className="bp-field__label">{item}</span>
                                  <textarea rows={2} maxLength={800}
                                    value={supplementAnswers[`${field.field_id}:${item}`] || ''}
                                    placeholder="해당 정보가 있다면 입력해 주세요. 추측해서 작성하지 않습니다."
                                    onChange={(event) => setSupplementAnswers((current) => ({
                                      ...current, [`${field.field_id}:${item}`]: event.target.value,
                                    }))} />
                                </label>
                              ))}
                          </React.Fragment>
                        )}
                      </div>
                    ))}
                  </div>
                  <nav className="bp-supplement__navigation" aria-label="계획 보완 페이지 탐색">
                    <button type="button" className="exp-upload" disabled={currentSupplementPage === 0}
                      onClick={() => setSupplementPage(currentSupplementPage - 1)}>← 이전</button>
                    <span>{currentSupplementPage + 1} / {supplementPages.length}</span>
                    {currentSupplementPage < supplementPages.length - 1 ? (
                      <button type="button" className="exp-upload"
                        onClick={() => setSupplementPage(currentSupplementPage + 1)}>다음 →</button>
                    ) : (
                      <button type="button" className="exp-upload" onClick={completeSupplement}
                        disabled={generating}>{generating ? '초안 작성 중…' : '보완 내용 반영하고 초안 만들기'}</button>
                    )}
                  </nav>
                </React.Fragment>
              )}
            </section>
          )}

          {active === 'preview' && (
            <section className="bp-eval">
              <h3 className="bp2__stepttl">초안 평가</h3>
              <p className="bp2__stepdesc">{evaluationBasis} 기준의 AI 예비진단 결과를 확인하세요.</p>

              {!plan ? (
                <div className="bp2__empty">
                  <p>먼저 AI 초안을 만들어야 예비진단을 받을 수 있어요.</p>
                  <button type="button" className="exp-upload" onClick={() => goStep('setup')}>← 공고 양식 선택으로 이동</button>
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
                    실제 심사 결과가 아니라 AI가 초안과 적용된 기준으로 매긴 참고용 자체 점검이에요.
                    제출 전 관련 전문가의 검토를 함께 받아 보세요.
                  </p>
                  <button type="button" className="exp-excel" onClick={runEvaluate}>🔄 다시 진단받기</button>
                  <button type="button" className="exp-upload" onClick={() => goStep('improve')}>초안 수정하기 ›</button>
                </React.Fragment>
              )}
            </section>
          )}

          {active === 'improve' && (
            <section>
              <h3 className="bp2__stepttl">초안 수정</h3>
              <p className="bp2__stepdesc">평가 내용을 참고해 항목을 수정하세요. 제목에 마우스를 올리거나 키보드로 선택하면 해당 평가를 볼 수 있습니다.</p>
              {!plan || !evalResult ? (
                <div className="bp2__empty">
                  <p>초안을 평가한 뒤 계획을 보완할 수 있어요.</p>
                  <button type="button" className="exp-upload" onClick={() => goStep('preview')}>← 초안 평가로 이동</button>
                </div>
              ) : (
                <React.Fragment>
                  <div className="bp-revise">
                    {revisionSections.map((section) => {
                      const feedback = evalResult.sections.find((item) => item.key === section.key)
                        || evalResult.sections.find((item) => item.label === section.label);
                      const analyzed = fieldAnalysis.find((item) => item.field_id === section.key);
                      return (
                        <div className="bp-revise__item" key={section.key}>
                          <div className="bp-revise__heading" tabIndex={0}
                            aria-label={feedback
                              ? `${section.label}, ${feedback.score}점. 잘된 점: ${feedback.strengths}. 보완할 점: ${feedback.improvements}`
                              : section.label}>
                            <span>{fieldLabel(section.label)}</span>
                            {feedback && <span className="bp-revise__score">{feedback.score}점 · 평가 보기</span>}
                            {feedback && (
                              <div className="bp-revise__tooltip" role="tooltip">
                                <strong>{feedback.score}점</strong>
                                <p>잘된 점: {feedback.strengths}</p>
                                <p>보완할 점: {feedback.improvements}</p>
                              </div>
                            )}
                          </div>
                          {analyzed?.type === 'image' ? (
                            <div className="bp-supplement__attachment">
                              {visibleImages[section.key] && (
                                <img className="bp-supplement__image" alt={fieldLabel(section.label)}
                                  src={`data:${visibleImages[section.key].mimeType};base64,${visibleImages[section.key].contentBase64}`} />
                              )}
                              <button type="button" className="bp-table__add" onClick={() => goStep('supplement')}>
                                계획 보완에서 이미지 {visibleImages[section.key] ? '변경' : '첨부'}
                              </button>
                            </div>
                          ) : analyzed?.status === 'unsupported' || analyzed?.status === 'non_input' ? (
                            <p className="bp-hint">{analyzed.missing_reason || '원본 양식에서 직접 확인할 항목입니다.'}</p>
                          ) : tableColumns(section.label).length ? (
                            <TableSection section={section}
                              onChange={(value) => onSectionChange(section.key, value)} />
                          ) : analyzed?.type === 'text' || analyzed?.type === 'metadata' ? (
                            <input className="bp2__psst-textarea" type="text" maxLength={5000}
                              aria-label={`${fieldLabel(section.label)} 내용 수정`}
                              value={section.content}
                              onChange={(event) => onSectionChange(section.key, event.target.value)} />
                          ) : (
                            <textarea className="bp2__psst-textarea" rows={reviewRows(section.content, 5)}
                              aria-label={`${fieldLabel(section.label)} 내용 수정`}
                              maxLength={5000} value={section.content}
                              onChange={(event) => onSectionChange(section.key, event.target.value)} />
                          )}
                        </div>
                      );
                    })}
                  </div>
                  <button type="button" className="exp-upload" onClick={regeneratePlan} disabled={generating}>
                    보완 내용으로 초안 다시 생성하기
                  </button>
                </React.Fragment>
              )}
            </section>
          )}

          {active === 'done' && (
            <section>
              <h3 className="bp2__stepttl">재평가 및 저장</h3>
              {!finalPlan ? (
                <div className="bp2__empty">
                  <p>초안 수정을 마치고 초안을 다시 생성해 주세요.</p>
                  <button type="button" className="exp-upload" onClick={() => goStep('improve')}>← 초안 수정으로 이동</button>
                </div>
              ) : (
                <React.Fragment>
                  {finalEvaluating ? (
                    <AnalyzingPanel title="보완 초안을 재평가하고 있어요" sub="수정한 내용을 기준으로 점수와 총평을 확인하고 있어요…" />
                  ) : finalEvalResult ? (
                    <div className="bp-eval__summary">
                      <ScoreGauge score={finalEvalResult.overallScore} />
                      <div>
                        <p className="bp-eval__ttl">재평가 결과</p>
                        <p className="bp-eval__comment">{finalEvalResult.overallComment}</p>
                      </div>
                    </div>
                  ) : (
                    <button type="button" className="exp-upload" onClick={runFinalEvaluate}>재평가 다시 시도하기</button>
                  )}
                  {finalEvalResult && (
                    <React.Fragment>
                      <p className="bp-summary">{finalPlan.summary}</p>
                      <div className="bp-actions">
                        <button type="button" className="exp-upload" onClick={() => downloadMarkdown(form, finalPlan)}>
                          📄 텍스트 초안 다운로드 (.md)
                        </button>
                        {(!templateInfo || templateInfo.outputFormats.includes('hwpx')) && (
                          <button type="button" className="exp-upload" onClick={() => renderPlan('hwpx')} disabled={!!renderingFormat}>
                            {renderingFormat === 'hwpx' ? 'HWPX 생성 중…' : 'HWPX 다운로드'}
                          </button>
                        )}
                        {(!templateInfo || templateInfo.outputFormats.includes('pdf')) && (
                          <button type="button" className="exp-upload" onClick={() => renderPlan('pdf')} disabled={!!renderingFormat}>
                            {renderingFormat === 'pdf' ? 'PDF 생성 중…' : 'PDF 다운로드'}
                          </button>
                        )}
                      </div>
                      <p className="bp-disclaimer">{templateInfo
                        ? '비어 있는 항목은 제출 전에 확인하고 채워 주세요.'
                        : "'정보 부족'으로 표시된 내용은 제출 전에 확인하고 채워 주세요."}</p>
                    </React.Fragment>
                  )}
                </React.Fragment>
              )}
            </section>
          )}

        </main>
      </div>
          {announcementPickerOpen && (
            <div className="bp-announcement-picker" role="dialog" aria-modal="true" aria-labelledby="bp-announcement-picker-title"
              onMouseDown={(event) => event.target === event.currentTarget && setAnnouncementPickerOpen(false)}>
              <section className="bp-announcement-picker__panel">
                <header className="bp-announcement-picker__header">
                  <div>
                    <h3 id="bp-announcement-picker-title">공고 선택</h3>
                    <p>저장한 공고를 먼저 보여드리고, 나머지는 관련도순으로 보여드려요.</p>
                  </div>
                  <button type="button" onClick={() => setAnnouncementPickerOpen(false)} aria-label="공고 선택 창 닫기">×</button>
                </header>
                <input className="bp-announcement-picker__search" type="search" value={pickerQuery}
                  onChange={(event) => setPickerQuery(event.target.value)} placeholder="공고명, 기관, 업종 검색"
                  aria-label="공고 검색" autoFocus />
                <div className="bp-announcement-picker__results" onScroll={(event) => {
                  const list = event.currentTarget;
                  if (list.scrollHeight - list.scrollTop - list.clientHeight < 160) loadMorePickerPolicies();
                }}>
                  {pickerSaveError && <p className="cal__err">{pickerSaveError}</p>}
                  {pickerError && <p className="cal__err">{pickerError}</p>}
                  {savedPickerItems.length + relatedPickerItems.length > 0 ? (
                    <AnnouncementCards items={[...savedPickerItems, ...relatedPickerItems]} savedIds={savedPolicyIds}
                      selectedPolicyId={selectedAnnouncement?.policyId} savingId={savingPolicyId}
                      selectingId={selectingPolicyId} onShowDetail={setDetailPolicy}
                      onChoose={chooseAnnouncement} onToggleSave={togglePickerSave} />
                  ) : !pickerLoading && !pickerError && (
                    <div className="gov__empty">{pickerQuery.trim() ? '검색 결과가 없어요.' : '표시할 공고가 없어요.'}</div>
                  )}
                  {pickerLoading && <p className="bp-hint" role="status">공고를 불러오고 있어요…</p>}
                  {pickerHasMore && !pickerLoading && (
                    <button type="button" className="bp-announcement-picker__more" onClick={loadMorePickerPolicies}>공고 더 보기</button>
                  )}
                </div>
              </section>
            </div>
          )}
          {detailPolicy && (
            <GovDetailModal item={detailPolicy} saved={savedPolicyIds.has(Number(detailPolicy.policyId))}
              saving={savingPolicyId === detailPolicy.policyId} onToggleSave={togglePickerSave}
              onClose={() => setDetailPolicy(null)} />
          )}
          {(generating || analyzingFields) && (
        <div className="bp2__loading-backdrop">
          <div className="bp2__loading-dialog" role="dialog" aria-modal="true"
            aria-label={analyzingFields ? '양식 분석 중' : '초안 작성 중'}>
            <AnalyzingPanel
              title={analyzingFields ? '양식의 입력 영역을 분석하고 있어요'
                : active === 'improve' ? '수정 내용을 반영해 초안을 다시 만들고 있어요' : 'AI가 초안을 작성하고 있어요'}
              sub={analyzingFields ? '각 칸에 필요한 정보와 누락된 내용을 확인하고 있어요…'
                : '입력한 내용과 양식에 맞춰 사업계획서 항목을 채우고 있어요…'}
            />
          </div>
        </div>
      )}
    </div>
  );
}
