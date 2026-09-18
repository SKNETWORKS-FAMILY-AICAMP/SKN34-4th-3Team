import React, { useState, useEffect } from 'react';
import { GOV_RULES, GOV_CHIPS, DEFAULT_BIZ, DEFAULT_REGION, NO_EVENTS } from '../constants.js';
import { api, useApi } from '../api.js';
import { eventsByDate, policyDday, policyDdayLabel, toPolicies } from '../utils.js';
import { AiConsult } from '../components/AiConsult.jsx';
import { Calendar } from './Home.jsx';

function safeOriginalUrl(item) {
  const candidates = [item && item.sourceUrl, item && item.source];
  for (const candidate of candidates) {
    if (!candidate) continue;
    try {
      const url = new URL(candidate);
      if (url.protocol === 'http:' || url.protocol === 'https:') return url.href;
    } catch {
      /* URL이 아닌 출처명은 버튼 링크로 사용하지 않는다. */
    }
  }
  return '';
}

export function OriginalButton({ item, className }) {
  const url = safeOriginalUrl(item);
  return url ? (
    <a className={className} href={url} target="_blank" rel="noreferrer">원문 확인하기</a>
  ) : (
    <button type="button" className={className} disabled title="등록된 원문 주소가 없습니다">
      원문 확인하기
    </button>
  );
}

export function GovDetailModal({ item, saved, saving, onToggleSave, onClose }) {
  const [detail, setDetail] = useState(null);
  const [summary, setSummary] = useState(null);
  const [summaryState, setSummaryState] = useState('loading');
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => {
    let alive = true;
    const ctl = new AbortController();
    setDetail(null);
    setSummary(null);
    setSummaryState('loading');

    (async () => {
      try {
        const result = await api.policy(item.policyId, { signal: ctl.signal });
        if (!alive) return;
        setDetail(result);
        if (!result.announcementId) {
          setSummaryState('unavailable');
          return;
        }
        try {
          const generated = await api.announcementSummary(result.announcementId, { signal: ctl.signal });
          if (!alive) return;
          setSummary(generated);
          setSummaryState('ready');
        } catch {
          if (alive) setSummaryState('unavailable');
        }
      } catch {
        if (alive) setSummaryState('unavailable');
      }
    })();

    return () => {
      alive = false;
      ctl.abort();
    };
  }, [item.policyId]);

  const dday = policyDday(item.applyEndDate);
  const matchingReasons = item.why || [];
  const detailPolicy = detail && detail.policy;
  const benefit = summary?.benefit || detailPolicy?.benefit || item.benefit || '공고문 확인 필요';
  const target = summary?.target || detailPolicy?.target || item.target || '공고문 확인 필요';
  const period = summary?.period || detail?.applyPeriod || '';
  const sourceLabel = item.source && !safeOriginalUrl({ source: item.source })
    ? item.source
    : '공고 제공기관';
  return (
    <div
      className="govm"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="govm-title"
    >
      <div className="govm__box">
        <button type="button" className="govm__close" onClick={onClose} aria-label="닫기">×</button>
        {/* 스크롤은 안쪽에서만 — 바깥 박스가 둥근 모서리를 그대로 유지한다 */}
        <div className="govm__scroll">
        <span className="govm__tag">{[item.industry, item.region].filter(Boolean).join(' · ') || '지원사업'}</span>
        <h2 id="govm-title" className="govm__title">{item.title}</h2>
        <p className="govm__agency">{sourceLabel}</p>

        <p className={'govm__summary-state is-' + summaryState} role="status" aria-live="polite">
          {summaryState === 'loading'
            ? 'AI가 공고문을 항목별로 요약하고 있어요…'
            : summaryState === 'ready'
              ? 'AI 공고 요약'
              : 'AI 요약을 불러오지 못해 공고 등록 정보를 표시해요.'}
        </p>

        <dl className="govm__rows">
          <div><dt>지원 내용</dt><dd title={benefit}>{benefit}</dd></div>
          <div><dt>지원 대상</dt><dd title={target}>{target}</dd></div>
          <div><dt>접수 마감</dt>
            <dd className={dday === null ? '' : 'govm__dday'}>
              {policyDdayLabel(dday)}
            </dd>
          </div>
          {period && <div><dt>신청 기간</dt><dd>{period}</dd></div>}
          {summary?.documents && <div><dt>제출 서류</dt><dd>{summary.documents}</dd></div>}
          {summary?.notes && <div><dt>유의사항</dt><dd>{summary.notes}</dd></div>}
        </dl>

        {matchingReasons.length > 0 && (
          <div className="govm__sec">
            <h3>내 조건과 맞는 점</h3>
            <div className="govm__chips">
              {matchingReasons.map((w) => <span key={w} className="govm__chip">{w}</span>)}
            </div>
          </div>
        )}

        {detail && detail.applyMethod && (
          <div className="govm__sec">
            <h3>신청 방법</h3>
            <p>{detail.applyMethod}</p>
          </div>
        )}

        <div className="govm__actions">
          <OriginalButton item={item} className="govm__original" />
          <button
            type="button"
            className={'govm__save' + (saved ? ' is-saved' : '')}
            disabled={saving}
            onClick={() => onToggleSave(item)}
          >
            {saving ? '처리 중…' : saved ? '★ 저장됨' : '☆ 관심 공고로 저장'}
          </button>
        </div>
        </div>
      </div>
    </div>
  );
}

export function AnnouncementAnalyzer({ user, onRequireLogin, savedPolicies = [], onToggleSavedPolicy }) {
  const [openGov, setOpenGov] = useState(null); // 상세 모달로 열어 둔 공고
  const [savingId, setSavingId] = useState(null);
  const [saveErr, setSaveErr] = useState('');
  // 마이페이지 AI 추천 공고와 같은 API·개수·정렬 결과를 사용한다.
  const profile = user || { biz: DEFAULT_BIZ, region: DEFAULT_REGION };
  const { data: recommended, loading, source } = useApi(
    `/policies/recommendations?limit=20&viewer=${user?.id || 'guest'}`,
    null,
    toPolicies
  );
  const savedIds = new Set(savedPolicies.map((p) => p.policyId));
  const { data: fetchedCalendar } = useApi('/calendar', NO_EVENTS, eventsByDate);
  const calendarEvents = React.useMemo(() => {
    const visible = {};
    for (const [date, items] of Object.entries(fetchedCalendar || {})) {
      const shown = items.filter(
        (event) =>
          event.mine ||
          event.type === 'tax' ||
          (event.policyId != null && savedIds.has(event.policyId))
      );
      if (shown.length) visible[date] = shown;
    }
    return visible;
  }, [fetchedCalendar, savedPolicies]);

  const toggleSave = async (item) => {
    if (!user) {
      onRequireLogin && onRequireLogin();
      return;
    }
    setSaveErr('');
    setSavingId(item.policyId);
    try {
      await onToggleSavedPolicy(item);
    } catch {
      setSaveErr('저장 상태를 변경하지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setSavingId(null);
    }
  };

  const recommendationWhy = (p) => {
    const dday = policyDday(p.applyEndDate);
    return [
      p.region,
      p.industry,
      p.eligible === true && '자격 충족',
      dday !== null && dday >= 0 && dday <= 30 && `마감 D-${dday}`,
    ].filter(Boolean);
  };

  return (
    <div className="az2">
      <div className="az2__cols">
        <div className="az2__card">
          <h3 className="az2__cardttl">추천 공고</h3>
          <p className="az2__note">
            {profile.biz} · {profile.region} 조건에 맞는 공고를 적합도 순으로 모았어요.
          </p>
          {!user ? (
            <div className="gov__empty">
              맞춤 추천과 관심 공고 저장은 로그인 후 이용할 수 있어요.
              <button type="button" className="az2__login" onClick={onRequireLogin}>로그인</button>
            </div>
          ) : loading ? (
            <div className="gov__empty">추천 공고를 불러오는 중이에요.</div>
          ) : source !== 'api' ? (
            <div className="gov__empty">추천 공고를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.</div>
          ) : recommended.length === 0 ? (
            <div className="gov__empty">조건에 맞는 추천 공고가 없어요.</div>
          ) : (
            <ul className="az2__reclist">
              {recommended.map((p) => {
                const dday = policyDday(p.applyEndDate);
                const saved = savedIds.has(p.policyId);
                const sourceLabel = p.source && !safeOriginalUrl({ source: p.source })
                  ? p.source
                  : [p.region, p.industry].filter(Boolean).join(' · ') || '지원사업 공고';
                return (
                  <li key={p.policyId}>
                    <div className="az2__recinfo">
                      <span className="az2__recmain">
                        <span className="az2__rectitle">{p.title}</span>
                        <span className="az2__recmeta">{sourceLabel}</span>
                      </span>
                      <b className="az2__recscore u-num">{policyDdayLabel(dday)}</b>
                    </div>
                    <div className="az2__recactions">
                      <button
                        type="button"
                        className="az2__action"
                        onClick={() => setOpenGov({ ...p, why: recommendationWhy(p) })}
                      >
                        상세 보기
                      </button>
                      <OriginalButton item={p} className="az2__action" />
                      <button
                        type="button"
                        className={'az2__action az2__save' + (saved ? ' is-saved' : '')}
                        aria-label={`${p.title} ${saved ? '저장 해제' : '저장'}`}
                        aria-pressed={saved}
                        disabled={savingId === p.policyId}
                        onClick={() => toggleSave(p)}
                      >
                        {saved ? '★ 저장됨' : '☆ 저장'}
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
          {saveErr && <p className="az2__saveerr">{saveErr}</p>}
        </div>

        <Calendar compact events={calendarEvents} />
      </div>

      <div className="az2__chat">
        <div className="chatpanel__hd">공고 상담</div>
        <AiConsult
          user={profile}
          onRequireLogin={onRequireLogin}
          rules={GOV_RULES}
          suggestions={GOV_CHIPS}
          title="공고지원 AI"
          category="policy"
          compact
          noHeader
        />
      </div>

      {openGov && (
        <GovDetailModal
          item={openGov}
          saved={savedIds.has(openGov.policyId)}
          saving={savingId === openGov.policyId}
          onToggleSave={toggleSave}
          onClose={() => setOpenGov(null)}
        />
      )}
    </div>
  );
}
