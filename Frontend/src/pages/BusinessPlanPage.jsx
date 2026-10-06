import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { api } from '../api.js';
import { INDUSTRIES, REGIONS } from '../constants.js';
import { linkBtn } from '../utils.js';
import { GuideTour } from '../components/GuideTour.jsx';
import { isWebApp } from '../web/env.js';
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

// 단계별 섹션 카드. tone은 색 계열(a=파랑, b=보라, c=회색). 사이드 메뉴·카드 머리글이 같은 값을 쓴다.
const STEP_SECTIONS = {
  refine: [
    { id: 'basic', letter: 'A', tone: 'a', title: '기초 정보', menu: 'A · 기초 정보', desc: '사업의 기본 사항을 선택하고 입력해요' },
    { id: 'idea', letter: 'B', tone: 'b', title: '아이디어 정리', menu: 'B · 아이디어 정리', desc: '누구의 어떤 문제를 어떻게 풀고, 어떻게 수익을 내는지 적어요' },
    { id: 'extra', letter: 'C', tone: 'c', title: '추가 설명 (선택)', menu: 'C · 추가 설명', desc: '초안에 더 반영하고 싶은 내용이 있으면 적어요' },
  ],
  // 시안이 정한 설명 문구가 없어 제목만 둔다.
  setup: [
    { id: 'announcement', letter: 'A', tone: 'a', title: '제출할 공고 (선택)', menu: 'A · 제출할 공고' },
    { id: 'template', letter: 'B', tone: 'b', title: '사업계획서 양식 (선택 · PDF/HWPX)', menu: 'B · 사업계획서 양식' },
  ],
};

// 단계별 화면 안내. 각 단계에 처음 들어왔을 때 한 번만 자동으로 띄우고, 이후에는 '사용 가이드' 버튼으로만 연다.
// 대상 요소가 지금 화면에 없는 항목(예: 진단 전의 결과 목록)은 투어가 건너뛴다.
const TOUR_KEY = (userId, step) => `changeup:bizplan-tour:v2:${userId}:${step}`;
const LEGACY_TOUR_KEY = (userId) => `changeup:bizplan-tour:v1:${userId}`;
const HELP_TOUR_STEP = {
  target: '.tour-fab',
  title: '가이드 다시 보기',
  body: <p>사용법이 궁금하면 언제든 오른쪽 아래 이 버튼을 눌러 지금 단계의 안내를 다시 볼 수 있어요.</p>,
};
const REFINE_TOUR = [
  {
    target: null,
    title: '사업계획서 초안, 이렇게 만들어요',
    body: (
      <React.Fragment>
        <p>아이디어를 입력하면 AI가 사업계획서 초안을 쓰고, 평가와 수정까지 도와드려요.</p>
        <ol className="gt__flow">
          <li><b>계획 정리</b>기초 정보와 아이디어 입력</li>
          <li><b>공고·양식 선택</b>제출할 공고와 양식 고르기(선택)</li>
          <li><b>초안 평가</b>AI 예비진단 확인</li>
          <li><b>초안 수정</b>평가를 보며 다듬기</li>
          <li><b>재평가 및 저장</b>PDF·HWPX로 내려받기</li>
        </ol>
      </React.Fragment>
    ),
  },
  {
    target: '[data-tour="crumbs"]',
    title: '진행 단계',
    body: <p>지금 있는 단계가 파란색으로 표시돼요. 끝낸 단계는 눌러서 언제든 돌아갈 수 있어요.</p>,
  },
  {
    target: '[data-tour="secnav"]',
    title: '섹션 이동',
    body: <p>누르면 해당 입력 카드로 바로 이동해요. 스크롤하면 지금 보고 있는 섹션이 표시돼요.</p>,
  },
  {
    target: '#bp-sec-basic',
    title: 'A. 기초 정보',
    body: <p>사업명, 창업 상태·업종·지역·형태, 팀 구성을 입력해요. 카드 오른쪽 위 버튼으로 접고 펼칠 수 있어요.</p>,
  },
  {
    target: '#bp-sec-idea',
    title: 'B. 아이디어 정리',
    body: <p>6개 항목을 편하게 적어 주세요. 칸은 글 길이에 맞춰 늘어나고, 거친 문장도 AI가 초안에 맞게 다듬어 줘요.</p>,
  },
  {
    target: '#bp-sec-extra',
    title: 'C. 추가 설명 (선택)',
    body: <p>초안에 꼭 넣고 싶은 내용이 있다면 적어 주세요. 비워 둬도 괜찮아요.</p>,
  },
  {
    target: '[data-tour="cta"]',
    title: 'AI로 입력 정리하기',
    body: <p>A·B의 필수 항목을 모두 채우면 버튼이 켜져요. 정리된 내용은 확인하고 직접 고칠 수 있어요.</p>,
  },
  {
    target: '[data-tour="save"]',
    title: '임시저장',
    body: <p>작성 중인 내용을 계정에 저장해요. 다음에 들어오면 이어서 쓸 수 있어요.</p>,
  },
  HELP_TOUR_STEP,
];

const TOURS = {
  refine: REFINE_TOUR,
  setup: [
    {
      target: '#bp-sec-announcement',
      title: 'A. 제출할 공고 (선택)',
      body: <p>지원할 공고를 고르면 그 공고의 평가 기준에 맞춰 초안을 쓰고 진단해요. 정해진 공고가 없으면 '공고 선택 안 함'을 고르세요.</p>,
    },
    {
      target: '#bp-sec-template',
      title: 'B. 사업계획서 양식 (선택)',
      body: <p>제출용 PDF·HWPX 양식을 끌어다 놓으면 양식의 칸에 맞춰 초안을 채워요. 양식이 없으면 기본 PSST 양식으로 만들어요.</p>,
    },
    {
      target: '[data-tour="cta"]',
      title: 'AI 초안 만들기',
      body: <p>계획 정리를 마쳤다면 눌러 주세요. 양식을 올렸다면 먼저 양식을 분석하고, 초안 작성에는 1분 정도 걸려요.</p>,
    },
    {
      target: '[data-tour="prev"]',
      title: '이전 단계로',
      body: <p>앞 단계의 내용을 고치고 싶으면 언제든 눌러 돌아갈 수 있어요. 입력한 내용은 그대로 남아요.</p>,
    },
    HELP_TOUR_STEP,
  ],
  supplement: [
    {
      target: '[data-tour="panel"]',
      title: '계획 보완',
      body: <p>선택한 양식에서 정보가 더 필요한 칸만 모았어요. 칸마다 내용을 입력하거나, 모르는 정보는 '현재 정보 없음'·'해당 사항 없음'을 골라 비워 둘 수 있어요.</p>,
    },
    {
      target: '[data-tour="next"]',
      title: '다음 단계로',
      body: <p>입력을 마치면 다음 단계로 넘어가 초안 평가를 받아요. 입력한 내용은 임시저장으로 보관할 수 있어요.</p>,
    },
  ],
  preview: [
    {
      target: '[data-tour="panel"]',
      title: '초안 평가',
      body: <p>AI가 선택한 공고·양식 기준으로 초안을 예비진단해요. 종합 점수와 총평을 먼저 확인하세요.</p>,
    },
    {
      target: '.bp-eval__list',
      title: '항목별 진단',
      body: <p>항목마다 점수, 잘된 점(👍), 보완할 점(🔧)을 보여줘요. 점수가 낮은 항목부터 고치면 효과가 커요.</p>,
    },
    {
      target: '[data-tour="next"]',
      title: '초안 수정으로',
      body: <p>진단 내용을 확인했다면 다음 단계에서 초안을 직접 고쳐요. 참고용 자체 점검이니 실제 심사와 다를 수 있어요.</p>,
    },
  ],
  improve: [
    {
      target: '[data-tour="panel"]',
      title: '초안 수정',
      body: <p>항목별 초안을 직접 고칠 수 있어요. 평가에서 지적된 부분을 보완해 주세요.</p>,
    },
    {
      target: '.bp-revise__score',
      title: '평가 다시 보기',
      body: <p>점수에 마우스를 올리거나 키보드로 선택하면 그 항목의 잘된 점과 보완할 점이 떠요.</p>,
    },
    {
      target: '[data-tour="regen"]',
      title: '초안 다시 생성하기',
      body: <p>수정을 마치면 눌러 주세요. 고친 내용을 반영해 초안을 다시 만들고 재평가까지 이어서 진행해요.</p>,
    },
  ],
  done: [
    {
      target: '[data-tour="panel"]',
      title: '재평가 및 저장',
      body: <p>수정한 초안의 재평가 점수와 총평을 확인하세요. 첫 진단과 비교해 얼마나 좋아졌는지 볼 수 있어요.</p>,
    },
    {
      target: '.bp-actions',
      title: '파일로 내려받기',
      body: <p>완성된 초안을 HWPX·PDF로 내려받아요. 비어 있거나 '정보 부족'으로 표시된 항목은 제출 전에 꼭 채워 주세요.</p>,
    },
    {
      target: '[data-tour="save"]',
      title: '임시저장',
      body: <p>지금까지의 작업을 계정에 저장해 두면 나중에 이어서 수정할 수 있어요.</p>,
    },
  ],
};

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

// 아이디어 정리 항목의 textarea: 내용에 맞춰 높이가 자동으로 늘어난다.
// field-sizing: content를 못 쓰는 브라우저를 위해 값이 바뀔 때마다 scrollHeight로 맞춘다.
function AutoTextarea({ value, onChange, ...rest }) {
  const ref = useRef(null);
  const fit = () => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = el.scrollHeight + 'px';
  };
  useLayoutEffect(fit, [value]);
  useEffect(() => {
    window.addEventListener('resize', fit);
    return () => window.removeEventListener('resize', fit);
  }, []);
  return (
    <textarea ref={ref} rows={1} value={value} {...rest}
      onChange={(event) => { onChange(event.target.value); fit(); }} />
  );
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

// AI가 일하는 동안 보여주는 애니메이션: 문서에 줄이 차례로 써지고 반짝이가 깜빡인다.
// 이 화면 전용 스타일(bp2__ai*)만 쓴다. 예전에는 지출관리 애니메이션 클래스를 빌려 써서,
// 그쪽 스타일이 바뀌면 함께 깨졌다.
function AnalyzingPanel({ title, sub }) {
  return (
    <div className="bp2__ai" role="status" aria-live="polite">
      <div className="bp2__ai-art" aria-hidden="true">
        <span className="bp2__ai-doc">
          <i />
          <i />
          <i />
          <i />
          <i />
        </span>
        <svg className="bp2__ai-spark bp2__ai-spark--a" viewBox="0 0 24 24" focusable="false">
          <path d="M12 1.5l2.6 7.9 7.9 2.6-7.9 2.6L12 22.5l-2.6-7.9L1.5 12l7.9-2.6z" fill="currentColor" />
        </svg>
        <svg className="bp2__ai-spark bp2__ai-spark--b" viewBox="0 0 24 24" focusable="false">
          <path d="M12 1.5l2.6 7.9 7.9 2.6-7.9 2.6L12 22.5l-2.6-7.9L1.5 12l7.9-2.6z" fill="currentColor" />
        </svg>
      </div>
      <div className="bp2__ai-text">
        <p className="bp2__ai-title">{title}</p>
        <p className="bp2__ai-sub">{sub}</p>
      </div>
      <span className="bp2__ai-bar" aria-hidden="true" />
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

// 섹션 카드: 색 띠 머리글(A/B/C 배지 + 제목 + 한 줄 설명) 아래에 본문. 사이드 메뉴가 id로 스크롤한다.
function SectionCard({ section, open = true, onToggle, children }) {
  const titleId = 'bp-sec-title-' + section.id;
  const bodyId = 'bp-sec-body-' + section.id;
  return (
    <section id={'bp-sec-' + section.id}
      className={'bp2__card bp2__card--' + section.tone + (open ? '' : ' is-collapsed')}
      aria-labelledby={titleId} data-bp-section={section.id}>
      <header className="bp2__card-head">
        <span className="bp2__badge" aria-hidden="true">{section.letter}</span>
        <div className="bp2__card-titles">
          <h3 id={titleId} className="bp2__card-title">{section.title}</h3>
          {section.desc && <p className="bp2__card-desc">{section.desc}</p>}
        </div>
        {onToggle && (
          <button type="button" className="bp2__toggle" aria-expanded={open} aria-controls={bodyId}
            aria-label={section.title + (open ? ' 접기' : ' 펼치기')} title={open ? '접기' : '펼치기'}
            onClick={onToggle}>
            <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" focusable="false">
              <path d="M5 8l5 5 5-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        )}
      </header>
      <div id={bodyId} className="bp2__collapse">
        <div className="bp2__collapse-in">
          <div className="bp2__card-body">{children}</div>
        </div>
      </div>
    </section>
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

export function BusinessPlanPage({ user, onRequireLogin, savedPolicies = [], onToggleSavedPolicy, onUnsavedChange }) {
  const userId = user && user.id;
  const mainRef = useRef(null);
  // 왼쪽 "섹션 이동" 메뉴에서 지금 보이는 섹션. 화면 상태일 뿐 작성 내용과는 무관하다.
  const [activeSection, setActiveSection] = useState('');
  const [tourOpen, setTourOpen] = useState(false);
  const [collapsed, setCollapsed] = useState({});
  const toggleCard = (id) => setCollapsed((prev) => ({ ...prev, [id]: !prev[id] }));
  const sectionLockRef = useRef(0);
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
  const [barMore, setBarMore] = useState(false); // 휴대폰 액션 바의 '더보기'(이전 단계 · 임시저장 등)
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
  const [templateDragOver, setTemplateDragOver] = useState(false);
  const templateInputRef = useRef(null);
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
  const fileOperationRef = useRef(false);
  const [draftLoaded, setDraftLoaded] = useState(false);
  const [editedBeforeLoad, setEditedBeforeLoad] = useState(false);
  const savedDraftRef = useRef(null);
  // 보관함(마이페이지 목록)에서 이 작성 화면이 가리키는 사업계획서. 처음 저장할 때 만들어진다.
  // 저장이 겹칠 때 먼저 만든 ID를 바로 보도록 ref로 둔다.
  const planIdRef = useRef(null);
  // 저장은 한 번에 하나씩 순서대로 보낸다(보관함 중복 생성·늦게 끝난 옛 저장의 덮어쓰기 방지).
  const saveQueueRef = useRef(Promise.resolve());
  const draftSnapshot = {
    form, plan, evalResult, revisionSections, finalPlan, finalEvalResult,
    selectedAnnouncementId, selectedAnnouncementInfo, refinedDone, templateInfo,
    fieldAnalysis, supplementAnswers, supplementImages, supplementChoices, editedSectionKeys,
  };
  const hasUnsavedChanges = !!(editedBeforeLoad || (draftLoaded && savedDraftRef.current
    && Object.keys(draftSnapshot).some((key) => draftSnapshot[key] !== savedDraftRef.current[key]
      && JSON.stringify(draftSnapshot[key]) !== JSON.stringify(savedDraftRef.current[key]))));

  useEffect(() => {
    if (draftLoaded && !savedDraftRef.current) savedDraftRef.current = draftSnapshot;
  }, [draftLoaded, draftSnapshot]);

  useEffect(() => {
    onUnsavedChange?.(hasUnsavedChanges);
  }, [hasUnsavedChanges, onUnsavedChange]);

  useEffect(() => () => onUnsavedChange?.(false), [onUnsavedChange]);

  useEffect(() => {
    if (!hasUnsavedChanges) return undefined;
    const warnBeforeUnload = (event) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warnBeforeUnload);
    return () => window.removeEventListener('beforeunload', warnBeforeUnload);
  }, [hasUnsavedChanges]);

  // 서버에서 받은 초안을 화면 상태로 되돌린다. 불러오는 동안 사용자가 고친 기초 정보는 유지한다.
  const applyDraft = (draft) => {
    planIdRef.current = Number.isInteger(draft.planId) ? draft.planId : null;
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
    savedDraftRef.current = null;
    setDraftLoaded(false);
    setEditedBeforeLoad(false);
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
        setDraftLoaded(true);
      });
    return () => { current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  useEffect(() => {
    if (mainRef.current) {
      mainRef.current.scrollTop = 0;
      // 화면은 페이지(.fp__body)가 스크롤되므로 단계가 바뀌면 그쪽도 맨 위로 올린다.
      const scroller = mainRef.current.closest('.fp__body');
      if (scroller) scroller.scrollTop = 0;
    }
  }, [active, supplementPage]);

  // 스크롤 위치에 따라 사이드 메뉴의 활성 섹션을 바꾼다(IntersectionObserver).
  useEffect(() => {
    const sections = STEP_SECTIONS[active];
    setActiveSection(sections ? sections[0].id : '');
    if (!sections || typeof IntersectionObserver === 'undefined') return undefined;
    const els = sections.map((sec) => document.getElementById('bp-sec-' + sec.id)).filter(Boolean);
    if (!els.length) return undefined;
    const scroller = els[0].closest('.fp__body');
    const visible = new Set();
    // 맨 아래까지 내렸는가(내용이 짧아 스크롤이 없는 화면은 제외).
    const atBottom = () => !!scroller && scroller.scrollTop > 0
      && scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 4;
    const pick = () => {
      if (Date.now() < sectionLockRef.current) return; // 메뉴를 눌러 스크롤하는 동안은 깜빡이지 않게 둔다
      // 짧은 마지막 카드는 관찰 구간에 못 들어오므로, 맨 아래면 마지막 섹션으로 본다.
      if (atBottom()) {
        setActiveSection(sections[sections.length - 1].id);
        return;
      }
      // 관찰 구간에 걸린 섹션이 여럿이면(앞 카드 끝 + 다음 카드 시작) 지금 읽는 쪽인 아래쪽을 고른다.
      const shown = sections.filter((sec) => visible.has(sec.id));
      if (shown.length) setActiveSection(shown[shown.length - 1].id);
    };
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        const id = entry.target.getAttribute('data-bp-section');
        if (entry.isIntersecting) visible.add(id); else visible.delete(id);
      });
      pick();
    }, { rootMargin: '-15% 0px -65% 0px', threshold: 0 });
    els.forEach((el) => io.observe(el));
    if (scroller) scroller.addEventListener('scroll', pick, { passive: true });
    return () => {
      io.disconnect();
      if (scroller) scroller.removeEventListener('scroll', pick);
    };
  }, [active, userId]);

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
    if (!draftLoaded) setEditedBeforeLoad(true);
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

  // 끌어다 놓기·삭제도 파일 선택 창과 같은 inspectTemplate을 거친다(선택 없음 = 파일 지우기).
  const onTemplateDrop = (event) => {
    event.preventDefault();
    setTemplateDragOver(false);
    if (inspectingTemplate) return;
    const files = event.dataTransfer && event.dataTransfer.files;
    if (files && files.length) inspectTemplate({ target: { files, value: '' } });
  };
  const removeTemplate = () => {
    if (templateInputRef.current) templateInputRef.current.value = '';
    inspectTemplate({ target: { files: [], value: '' } });
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

  const buildRenderPayload = (format) => ({
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

  const renderPlan = async (format) => {
    if (!finalPlan || fileOperationRef.current) return;
    fileOperationRef.current = true;
    setErr('');
    setRenderingFormat(format);
    try {
      const rendered = await api.renderBusinessPlan(buildRenderPayload(format));
      downloadBase64File(rendered);
    } catch (e2) {
      if (e2 && e2.status === 401) onRequireLogin && onRequireLogin();
      else setErr(e2.detail || `${format.toUpperCase()} 파일을 만들지 못했습니다. 잠시 후 다시 시도해 주세요.`);
    } finally {
      fileOperationRef.current = false;
      setRenderingFormat('');
    }
  };

  const goStep = (key) => {
    setErr('');
    setActive(key);
  };

  // 각 단계에 처음 들어왔을 때 한 번만 자동으로 안내를 띄운다(브라우저별 기록).
  // 띄우는 순간 본 것으로 기록하므로, 중간에 페이지를 나갔다 와도 다시 자동으로 뜨지 않는다.
  const aiBusy = generating || analyzingFields || refining;
  useEffect(() => {
    if (!userId || !TOURS[active] || aiBusy) return undefined;
    const key = TOUR_KEY(userId, active);
    try {
      if (localStorage.getItem(key) === 'done') return undefined;
      if (active === 'refine' && localStorage.getItem(LEGACY_TOUR_KEY(userId)) === 'done') {
        localStorage.setItem(key, 'done');
        return undefined;
      }
    } catch (e) {
      // 기록을 남길 수 없으면 들어올 때마다 뜨게 되므로 자동 안내를 하지 않는다.
      return undefined;
    }
    const t = setTimeout(() => {
      try {
        localStorage.setItem(key, 'done');
      } catch (e) {
        return;
      }
      setTourOpen(true);
    }, 600);
    return () => clearTimeout(t);
  }, [userId, active, aiBusy]);

  const closeTour = () => setTourOpen(false);

  const goSection = (id) => {
    const el = document.getElementById('bp-sec-' + id);
    if (!el) return;
    setCollapsed((prev) => (prev[id] ? { ...prev, [id]: false } : prev));
    const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    sectionLockRef.current = Date.now() + 900;
    setActiveSection(id);
    el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  };

  const saveNow = async () => {
    if (!userId) {
      onRequireLogin && onRequireLogin();
      return;
    }
    const snapshotToSave = draftSnapshot;
    const data = { ...snapshotToSave, supplementPage };
    const hasContent = !!plan || Object.values(form).some((v) => String(v || '').trim());
    const run = saveQueueRef.current.then(() => persistDraft(snapshotToSave, data, hasContent));
    saveQueueRef.current = run.catch(() => {});
    await run;
  };

  const persistDraft = async (snapshotToSave, data, hasContent) => {
    let note = '임시저장했어요 · 마이페이지에서 관리할 수 있어요';
    try {
      // 내용이 있으면 보관함에도 저장한다(없으면 새로 만들고, 마이페이지에서 지웠으면 다시 만든다).
      let id = planIdRef.current;
      if (hasContent) {
        try {
          id = id ? (await api.saveBizplanPlan(id, data)).id : (await api.createBizplanPlan(data)).id;
        } catch (e3) {
          if (!(e3 && e3.status === 404)) throw e3;
          id = (await api.createBizplanPlan(data)).id;
        }
        planIdRef.current = id;
      }
      await api.saveBizplanDraft({ ...data, ...(id ? { planId: id } : {}) });
      savedDraftRef.current = snapshotToSave;
      setEditedBeforeLoad(false);
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

  // 초안·평가·재평가 결과가 새로 나오면 자동으로 저장해 마이페이지 목록에 바로 반영한다.
  useEffect(() => {
    if (!draftLoaded || !savedDraftRef.current || !plan || !hasUnsavedChanges) return;
    saveNow();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan, evalResult, finalPlan, finalEvalResult]);

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
  const prevStep = activeIdx > 0 ? visibleSteps[activeIdx - 1] : null;
  const evaluationBasis = selectedAnnouncement
    ? `선택한 공고와 ${templateInfo ? '제출한 양식' : '기본 PSST 양식'}`
    : templateInfo ? '제출한 양식' : '기본 PSST 양식';
  // 화면에 보이는 단계 기준 번호. 현재 단계가 목록에 없으면 첫 단계로 본다.
  const currentIdx = Math.max(activeIdx, 0);
  const stepNo = currentIdx + 1;
  const stepSections = STEP_SECTIONS[active];
  const currentStep = visibleSteps[currentIdx];
  // 안내문: 지금 단계에서 다음 행동을 막고 있는 이유. 없으면 표시하지 않는다.
  const guideText = active === 'refine'
    ? (refinedDone ? 'AI 정리가 완료됐습니다. 내용을 검토하고 필요한 부분을 수정해 주세요.' : '')
    : active === 'setup' && !refinedDone
      ? '계획 정리에서 AI 정리를 완료해야 초안을 만들 수 있습니다.'
      : '';
  // 머리글과 타임라인이 같은 문구를 쓰도록 한 곳에서 정한다. 설명이 없는 단계는 빈 문자열.
  const stepDesc = (key) => ({
    setup: '공고와 양식은 선택 사항입니다. 양식이 없으면 기본 PSST 양식으로 초안을 만듭니다.',
    supplement: '선택한 양식에서 추가 정보가 필요한 입력 칸만 확인하세요. 모르는 정보는 비워 둘 수 있습니다.',
    preview: `${evaluationBasis} 기준의 AI 예비진단 결과를 확인하세요.`,
    improve: '평가 내용을 참고해 항목을 수정하세요. 제목에 마우스를 올리거나 키보드로 선택하면 해당 평가를 볼 수 있습니다.',
  }[key] || '');

  // 웹앱: 단계별 버튼을 본문 아래 액션 바 하나로 모은다.
  // 아직 안 한 단계 작업이 있으면 그 작업이, 끝났으면 다음 단계가 파란 주 버튼이 된다.
  const web = isWebApp();
  const stepAction = {
    refine: {
      run: runRefine, done: refinedDone, disabled: !basicReady || !ideaReady || refining,
      label: refining ? '입력 정리 중…' : refinedDone ? 'AI로 다시 정리' : 'AI로 입력 정리하기',
    },
    setup: {
      run: () => (templateInfo ? runTemplateAnalysis() : generatePlan()), done: !!plan,
      disabled: inspectingTemplate || analyzingFields || (!!templateFile && !templateInfo)
        || !basicReady || !ideaReady || !refinedDone || generating,
      label: analyzingFields ? '양식 입력 영역 분석 중…' : generating ? '초안 작성 중…'
        : templateInfo ? '양식 분석하고 초안 준비하기' : plan ? 'AI 초안 다시 만들기' : 'AI 초안 만들기',
    },
    supplement: { run: null, done: !!plan },
    preview: plan ? {
      run: runEvaluate, done: !!evalResult, disabled: evaluating,
      label: evaluating ? '진단 중…' : evalResult ? '다시 진단받기' : '예비진단 시작하기',
    } : { run: null, done: false },
    improve: plan && evalResult ? {
      run: regeneratePlan, done: !!finalPlan, disabled: generating, keepFocus: true,
      label: generating ? '초안 생성 중…' : '보완 내용으로 초안 다시 만들기',
    } : { run: null, done: false },
    done: { run: null, done: true },
  }[active] || { run: null, done: false };
  const actionIsPrimary = !!stepAction.run && !stepAction.done;

  const renderBasic = (field) => (
    <label key={field.key} className={'bp-field' + (field.key === 'businessName' || field.multiline ? ' bp2__full' : '')}>
      <span className="bp-field__label">{field.label}</span>
      <FieldControl field={field.key === 'industry' ? { ...field, options: industryOptions } : field}
        value={form[field.key]}
        onChange={(value) => setReviewedField(field.key, value)} />
    </label>
  );

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
      {/* 다른 페이지와 같은 자리(오른쪽 아래 다크모드 버튼 옆)의 가이드 다시 보기 버튼 */}
      <button type="button" className="tour-fab" onClick={() => setTourOpen(true)}
        aria-label={(currentStep ? currentStep.label : '사업계획서') + ' 가이드 보기'} title="사용 가이드">
        ?
      </button>
      <GuideTour open={tourOpen} steps={TOURS[active] || REFINE_TOUR} onClose={closeTour}
        label={(currentStep ? currentStep.label : '사업계획서') + ' 가이드'} />
      {/* 진행 단계 브레드크럼: 지금 단계 말고는 모두 눌러서 이동할 수 있다(다음 단계 버튼과 같은 동작). */}
      <nav className="bp2__crumbs" aria-label="진행 단계" data-tour="crumbs">
        <ol className="bp2__crumbs-in">
          {visibleSteps.map((step, i) => {
            const state = i < currentIdx ? 'done' : i === currentIdx ? 'current' : 'todo';
            return (
              <li key={step.key} className={'bp2__crumb is-' + state}
                aria-current={state === 'current' ? 'step' : undefined}>
                {state === 'current'
                  ? <span>{step.label}</span>
                  : <button type="button" onClick={() => goStep(step.key)}>{step.label}</button>}
              </li>
            );
          })}
        </ol>
      </nav>

      <div className="bp2__body">
        <aside className="bp2__side">
          <div className="bp2__title-block">
            <p className="bp2__eyebrow">STEP {stepNo}<span> / {visibleSteps.length}</span></p>
            <h2 className="bp2__side-title">{currentStep ? currentStep.label : ''}</h2>
            {stepDesc(active) && <p className="bp2__side-desc">{stepDesc(active)}</p>}
          </div>

          {stepSections && (
            <nav className="bp2__secnav" aria-label="섹션 이동" data-tour="secnav">
              <ul>
                {stepSections.map((sec) => (
                  <li key={sec.id}>
                    <button type="button" className={activeSection === sec.id ? 'is-on' : ''}
                      aria-current={activeSection === sec.id ? 'location' : undefined}
                      onClick={() => goSection(sec.id)}>
                      {sec.menu}
                    </button>
                  </li>
                ))}
              </ul>
            </nav>
          )}

          {!web && (
          <div className="bp2__actions">
            {active === 'refine' && (
              <button type="button" className="bp2__cta" data-tour="cta" onClick={runRefine}
                disabled={!basicReady || !ideaReady || refining}>
                {refining ? '입력 정리 중…' : refinedDone ? 'AI로 다시 정리하기' : 'AI로 입력 정리하기'}
              </button>
            )}
            {active === 'setup' && (
              <button type="button" className="bp2__cta" data-tour="cta"
                onClick={() => templateInfo ? runTemplateAnalysis() : generatePlan()}
                disabled={inspectingTemplate || analyzingFields || (!!templateFile && !templateInfo)
                  || !basicReady || !ideaReady || !refinedDone || generating}>
                {analyzingFields ? '양식 입력 영역 분석 중…' : generating ? '초안 작성 중…'
                  : templateInfo ? '양식 분석하고 초안 준비하기' : 'AI 초안 만들기'}
              </button>
            )}
            {nextStep && (
              <button type="button" className="bp2__next" data-tour="next" onClick={() => goStep(nextStep.key)}>
                다음 단계 · {nextStep.label} ›
              </button>
            )}
            {/* 보조 버튼(이전 단계·임시저장)은 같은 모양으로 한 줄에 나란히 둔다. */}
            <div className={'bp2__subactions' + (prevStep ? ' has-prev' : '')}>
              {prevStep && (
                <button type="button" className="bp2__prev" data-tour="prev" onClick={() => goStep(prevStep.key)}
                  title={`이전 단계 · ${prevStep.label}`}>
                  ‹ 이전 단계
                </button>
              )}
              <button type="button" className="bp2__save" data-tour="save" onClick={saveNow}>임시저장</button>
            </div>
            {savedNote && <span className="bp2__saved" role="status">{savedNote}</span>}
            {import.meta.env.DEV && (
              <button type="button" className="bp2__preset" onClick={applyTestPreset}>
                테스트용 프리셋 적용
              </button>
            )}
          </div>
          )}
          {guideText && <p className="bp2__guide">{guideText}</p>}
        </aside>

        <main className="bp2__main" ref={mainRef}>
          {err && <p className="cal__err">{err}</p>}

          {active === 'refine' && (
            <React.Fragment>
              <SectionCard section={STEP_SECTIONS.refine[0]} open={!collapsed[STEP_SECTIONS.refine[0].id]} onToggle={() => toggleCard(STEP_SECTIONS.refine[0].id)}>
                <div className="bp2__basic">
                  {BASIC_FIELDS.map(renderBasic)}
                </div>
              </SectionCard>
              <SectionCard section={STEP_SECTIONS.refine[1]} open={!collapsed[STEP_SECTIONS.refine[1].id]} onToggle={() => toggleCard(STEP_SECTIONS.refine[1].id)}>
                <div className="bp2__doc">
                  {IDEA_FIELDS.filter((field) => !field.optional).map((field, i) => (
                    <div key={field.key} className="bp2__doc-item">
                      <label htmlFor={'bp-idea-' + field.key} className="bp2__doc-head">
                        <span className="bp2__doc-no">{String(i + 1).padStart(2, '0')}</span>
                        <span className="bp2__doc-name">{field.label}</span>
                        <span className="bp2__doc-guide">{field.placeholder}</span>
                      </label>
                      <AutoTextarea id={'bp-idea-' + field.key} className="bp2__doc-text"
                        value={form[field.key]} placeholder={field.placeholder}
                        onChange={(value) => setReviewedField(field.key, value)} />
                    </div>
                  ))}
                </div>
              </SectionCard>
              <SectionCard section={STEP_SECTIONS.refine[2]} open={!collapsed[STEP_SECTIONS.refine[2].id]} onToggle={() => toggleCard(STEP_SECTIONS.refine[2].id)}>
                <div className="bp2__grid3 bp2__grid3--extra">
                  {IDEA_FIELDS.filter((field) => field.optional).map((field) => (
                    <label key={field.key} className="bp-field bp2__span3">
                      <span className="bp-field__label">{field.label}</span>
                      <FieldControl field={field} value={form[field.key]}
                        onChange={(value) => setReviewedField(field.key, value)} />
                    </label>
                  ))}
                </div>
              </SectionCard>
            </React.Fragment>
          )}

          {active === 'setup' && (
            <React.Fragment>
              <SectionCard section={STEP_SECTIONS.setup[0]}>
                {/* 실제 radio 기반이라 키보드로 고를 수 있다. 이미 선택된 카드를 다시 눌러도 공고 선택 창이 열리도록 onClick으로 처리한다. */}
                <div className="bp2__choices" role="radiogroup" aria-labelledby="bp-sec-title-announcement">
                  <label className={'bp2__choice' + (selectedAnnouncement ? ' is-selected' : '')}>
                    <input type="radio" name="bp-announcement" className="bp2__choice-input"
                      checked={!!selectedAnnouncement} onChange={() => {}} onClick={openAnnouncementPicker} />
                    <span className="bp2__radio" aria-hidden="true" />
                    <span className="bp2__choice-body">
                      <span className="bp2__choice-title">공고 선택</span>
                      <span className="bp2__choice-desc">지원할 공고를 골라 양식에 맞춰 작성합니다.</span>
                    </span>
                  </label>
                  <label className={'bp2__choice' + (!selectedAnnouncement ? ' is-selected' : '')}>
                    <input type="radio" name="bp-announcement" className="bp2__choice-input"
                      checked={!selectedAnnouncement} onChange={() => {}} onClick={clearAnnouncement} />
                    <span className="bp2__radio" aria-hidden="true" />
                    <span className="bp2__choice-body">
                      <span className="bp2__choice-title">공고 선택 안 함</span>
                      <span className="bp2__choice-desc">공고 없이 기본 양식으로 초안을 만듭니다.</span>
                    </span>
                  </label>
                </div>
                {selectedAnnouncement && (
                  <p className="bp-announcement-choice__selected" role="status">
                    선택한 공고: {selectedAnnouncement.title}
                  </p>
                )}
                {announcementError && <p className="cal__err">{announcementError}</p>}
              </SectionCard>

              <SectionCard section={STEP_SECTIONS.setup[1]}>
                {/* 기본 파일 입력은 숨기고, 드롭존의 "파일 선택" 버튼이 대신 연다. */}
                <input ref={templateInputRef} type="file" accept=".pdf,.hwpx" hidden
                  aria-labelledby="bp-sec-title-template" onChange={inspectTemplate} disabled={inspectingTemplate} />
                <div
                  className={'bp2__drop' + (templateDragOver ? ' is-over' : '') + (templateFile ? ' has-file' : '')}
                  onDragOver={(event) => { event.preventDefault(); setTemplateDragOver(true); }}
                  onDragLeave={() => setTemplateDragOver(false)}
                  onDrop={onTemplateDrop}
                >
                  {templateFile ? (
                    <div className="bp2__drop-info">
                      <span className="bp2__drop-name">{templateFile.name}</span>
                      <span className="bp2__drop-sub" role="status">
                        {inspectingTemplate
                          ? '분석 중…'
                          : templateInfo
                            ? `분석 완료 · ${templateInfo.fields?.length || 0}개 작성 항목을 찾았습니다.`
                            : ''}
                      </span>
                    </div>
                  ) : (
                    <p className="bp2__drop-info bp2__drop-empty">
                      선택된 파일 없음 · 양식을 선택하지 않으면 기본 PSST 항목을 사용합니다.
                    </p>
                  )}
                  <div className="bp2__drop-actions">
                    <button type="button" className="bp2__btn"
                      onClick={() => templateInputRef.current && templateInputRef.current.click()}
                      disabled={inspectingTemplate}>
                      {templateFile ? '다시 선택' : '파일 선택'}
                    </button>
                    {templateFile && (
                      <button type="button" className="bp2__btn bp2__btn--danger"
                        onClick={removeTemplate} disabled={inspectingTemplate}
                        aria-label={`${templateFile.name} 삭제`}>
                        삭제
                      </button>
                    )}
                  </div>
                </div>
                {templateError && <p className="cal__err">{templateError}</p>}
              </SectionCard>
            </React.Fragment>
          )}

          {active === 'supplement' && (
            <section className="bp2__panel" data-tour="panel">
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
            <section className="bp2__panel bp-eval" data-tour="panel">

              {!plan ? (
                <div className="bp2__empty">
                  <p>먼저 AI 초안을 만들어야 예비진단을 받을 수 있어요.</p>
                  <button type="button" className="exp-upload" onClick={() => goStep('setup')}>← 공고 양식 선택으로 이동</button>
                </div>
              ) : evaluating ? (
                <AnalyzingPanel title="AI가 예비진단을 하고 있어요" sub="항목별로 강점과 보완할 점을 살펴보고 있어요…" />
              ) : !evalResult ? (
                web
                  ? <p className="bp2__empty">초안이 준비됐어요. 아래 <b>예비진단 시작하기</b>를 누르면 항목별 점수와 보완할 점을 알려드려요.</p>
                  : <button type="button" className="exp-upload" onClick={runEvaluate}>🩺 예비진단 시작하기</button>
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
                  {!web && <button type="button" className="exp-excel" onClick={runEvaluate}>🔄 다시 진단받기</button>}
                  {!web && <button type="button" className="exp-upload" onClick={() => goStep('improve')}>초안 수정하기 ›</button>}
                </React.Fragment>
              )}
            </section>
          )}

          {active === 'improve' && (
            <section className="bp2__panel" data-tour="panel">
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
                  {!web && (
                    <button type="button" className="exp-upload" data-tour="regen" onMouseDown={(event) => event.preventDefault()}
                      onClick={regeneratePlan} disabled={generating}>
                      보완 내용으로 초안 다시 생성하기
                    </button>
                  )}
                </React.Fragment>
              )}
            </section>
          )}

          {active === 'done' && (
            <section className="bp2__panel" data-tour="panel">
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
                        {(!templateInfo || templateInfo.kind === 'hwpx') && (
                          <button type="button" className="exp-upload" onClick={() => renderPlan('hwpx')} disabled={!!renderingFormat}>
                            {renderingFormat === 'hwpx' ? 'HWPX 생성 중…' : 'HWPX 다운로드'}
                          </button>
                        )}
                        {(!templateInfo || templateInfo.kind === 'pdf') && (
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

          {web && (
            <div className={'bp2__bar' + (barMore ? ' is-more-open' : '')} role="group" aria-label="사업계획서 작업">
              {barMore && <div className="bp2__bar-dim" onClick={() => setBarMore(false)} aria-hidden="true" />}
              <button type="button" className="bp2__bar-more" aria-expanded={barMore}
                aria-label="더보기" onClick={() => setBarMore((v) => !v)}>⋯</button>
              {/* 보조 버튼: PC · 태블릿은 바 왼쪽에 나란히, 휴대폰은 '더보기'를 누르면 위로 펼쳐진다 */}
              <div className="bp2__bar-sub" onClick={() => setBarMore(false)}>
                {prevStep && (
                  <button type="button" className="bp2__bar-ghost" data-tour="prev" onClick={() => goStep(prevStep.key)}>
                    ‹ 이전 단계
                  </button>
                )}
                <button type="button" className="bp2__bar-ghost" data-tour="save" onClick={saveNow}>임시저장</button>
                {stepAction.run && !actionIsPrimary && (
                  <button type="button" className="bp2__bar-ghost" data-tour={active === 'improve' ? 'regen' : 'cta'} onClick={stepAction.run}
                    onMouseDown={stepAction.keepFocus ? (event) => event.preventDefault() : undefined}
                    disabled={stepAction.disabled}>
                    {stepAction.label}
                  </button>
                )}
                {nextStep && actionIsPrimary && (
                  <button type="button" className="bp2__bar-ghost" data-tour="next" onClick={() => goStep(nextStep.key)}>
                    건너뛰고 {nextStep.label} ›
                  </button>
                )}
              </div>
              {savedNote && <span className="bp2__saved" role="status">{savedNote}</span>}
              {actionIsPrimary ? (
                <button type="button" className="bp2__bar-main" data-tour={active === 'improve' ? 'regen' : 'cta'} onClick={stepAction.run}
                  onMouseDown={stepAction.keepFocus ? (event) => event.preventDefault() : undefined}
                  disabled={stepAction.disabled}>
                  {stepAction.label}
                </button>
              ) : nextStep ? (
                <button type="button" className="bp2__bar-main" data-tour="next" onClick={() => goStep(nextStep.key)}>
                  다음 단계 · {nextStep.label} ›
                </button>
              ) : null}
            </div>
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
          {(generating || analyzingFields || refining) && (
        <div className="bp2__loading-backdrop">
          <div className="bp2__loading-dialog" role="dialog" aria-modal="true"
            aria-label={refining ? '입력 정리 중' : analyzingFields ? '양식 분석 중' : '초안 작성 중'}>
            <AnalyzingPanel
              title={refining ? 'AI가 입력한 내용을 정리하고 있어요'
                : analyzingFields ? '양식의 입력 영역을 분석하고 있어요'
                : active === 'improve' ? '수정 내용을 반영해 초안을 다시 만들고 있어요' : 'AI가 초안을 작성하고 있어요'}
              sub={refining ? '기초 정보와 아이디어를 초안에 쓰기 좋게 다듬고 있어요…'
                : analyzingFields ? '각 칸에 필요한 정보와 누락된 내용을 확인하고 있어요…'
                : '입력한 내용과 양식에 맞춰 사업계획서 항목을 채우고 있어요…'}
            />
          </div>
        </div>
      )}
    </div>
  );
}
