import React, { useState, useEffect, useMemo, useRef } from 'react';
import { LogoMark, BrandWord } from '../components/LogoMark.jsx';
import { useApi, api } from '../api.js';
import {
  MP_MENU, MP_RECENT_MAX, CHATLOG_TABS,
  INDUSTRIES, REGIONS, WEEKDAYS, ROADMAP, ROADMAP_TASKS, NO_EVENTS,
} from '../constants.js';
import {
  pad2, dayKey, policyDday, policyDdayLabel, toPolicies, inputStyle, linkBtn,
  eventsByDate, upcomingCalendarEvents,
} from '../utils.js';
import { MenuDrawer } from '../components/MenuDrawer.jsx';
import { GovDetailModal, OriginalButton } from './AnnouncementAnalyzer.jsx';

export function MpCalendar({ full, savedPolicies = [], onEventsChanged }) {
  const today = new Date();
  const todayKey = `${today.getFullYear()}-${pad2(today.getMonth() + 1)}-${pad2(today.getDate())}`;
  const [cur, setCur] = useState({ y: today.getFullYear(), m: today.getMonth() });
  const [sel, setSel] = useState(todayKey);
  const [ftitle, setFtitle] = useState('');
  const [ftype, setFtype] = useState('tax');
  const [reload, setReload] = useState(0); // 등록·삭제 후 서버 일정을 다시 불러오기 위한 카운터
  const [calErr, setCalErr] = useState('');

  // Backend: GET /api/calendar → 세금·정책 일정 + 내가 등록한 일정(USER).
  // 내 일정을 서버에 저장하므로 공고지원 AI 화면의 달력에서도 같은 일정이 보인다.
  const { data: fetched } = useApi(
    `/calendar?year=${cur.y}&month=${cur.m + 1}&limit=200&r=${reload}`,
    NO_EVENTS,
    eventsByDate
  );

  // 이 달력은 내 일정·세금 신고일·저장한 공고 마감일을 보여준다.
  // 서버는 마감 전 공고를 전부 내려주므로 공고 마감일은 저장한 정책만 남긴다.
  const events = React.useMemo(() => {
    const savedIds = new Set(savedPolicies.map((p) => p.policyId));
    const o = {};
    for (const [k, arr] of Object.entries(fetched || {})) {
      const shown = arr.filter(
        (e) => e.mine || e.type === 'tax' || (e.policyId != null && savedIds.has(e.policyId))
      );
      if (shown.length) o[k] = shown;
    }
    return o;
  }, [fetched, savedPolicies]);

  const startDow = new Date(cur.y, cur.m, 1).getDay();
  const daysInMonth = new Date(cur.y, cur.m + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < startDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(null);

  const monthPrefix = `${cur.y}-${pad2(cur.m + 1)}`;
  const monthCount = Object.keys(events).filter((k) => k.startsWith(monthPrefix) && events[k].length).length;
  const shift = (delta) => {
    const nd = new Date(cur.y, cur.m + delta, 1);
    setCur({ y: nd.getFullYear(), m: nd.getMonth() });
  };
  const selEvents = events[sel] || [];
  const [sy, sm, sd] = sel.split('-').map(Number);
  const selLabel = `${sm}월 ${sd}일 (${WEEKDAYS[new Date(sy, sm - 1, sd).getDay()]})`;

  // 내 일정은 서버에 저장한다 → 공고지원 AI 화면의 달력에서도 그대로 보인다.
  const addEvent = async (e) => {
    e.preventDefault();
    const t = ftitle.trim();
    if (!t) return;
    setCalErr('');
    try {
      await api.calendarCreate({
        title: t,
        dueDate: sel,
        description: ftype === 'tax' ? '세금 일정' : '지원사업 일정',
      });
      setFtitle('');
      setReload((n) => n + 1);
      onEventsChanged && onEventsChanged();
    } catch (err) {
      setCalErr(
        err && err.status === 401
          ? '일정을 저장하려면 로그인이 필요해요.'
          : '일정을 저장하지 못했어요. 잠시 후 다시 시도해 주세요.'
      );
    }
  };

  const delEvent = async (idx) => {
    const target = (events[sel] || [])[idx];
    if (!target || target.id == null) return;
    setCalErr('');
    try {
      await api.calendarDelete(target.id);
      setReload((n) => n + 1);
      onEventsChanged && onEventsChanged();
    } catch (err) {
      setCalErr('일정을 삭제하지 못했어요. 잠시 후 다시 시도해 주세요.');
    }
  };

  return (
    <div className="cal" role="group" aria-label="일정 캘린더" style={full ? { maxWidth: 520 } : undefined}>
      <div className="cal__head">
        <h3 className="cal__title">일정 관리</h3>
        <div className="cal__nav">
          <button type="button" onClick={() => shift(-1)} aria-label="이전 달">‹</button>
          <span className="cal__month">{cur.y}.{pad2(cur.m + 1)}</span>
          <button type="button" onClick={() => shift(1)} aria-label="다음 달">›</button>
        </div>
      </div>
      <p className="cal__sub">이번 달 일정 {monthCount}건</p>
      <div className="cal__grid">
        {WEEKDAYS.map((w, i) => (
          <div key={w} className={'cal__dow' + (i === 0 ? ' cal__dow--sun' : '')}>{w}</div>
        ))}
        {cells.map((d, i) => {
          if (!d) return <div key={`e${i}`} className="cal__day cal__day--out" />;
          const k = dayKey(cur.y, cur.m, d);
          const types = [...new Set((events[k] || []).map((e) => e.type))];
          const isSel = k === sel;
          return (
            <button key={k} type="button"
              className={'cal__day' + (isSel ? ' cal__day--sel' : '') + (k === todayKey && !isSel ? ' cal__day--today' : '')}
              aria-pressed={isSel} onClick={() => setSel(k)}>
              {d}
              {types.length > 0 && (
                <span className="cal__dot">
                  {types.map((t) => <i key={t} className={t === 'tax' ? 't-tax' : 't-policy'} />)}
                </span>
              )}
            </button>
          );
        })}
      </div>
      <div className="cal__legend">
        <span><i className="t-tax" /> 세금</span>
        <span><i className="t-policy" /> 지원사업</span>
      </div>
      <div className="cal__events">
        <h4>{selLabel} 일정</h4>
        {/* 일정이 늘어나도 카드 높이는 그대로 두고 이 목록만 스크롤된다 */}
        <div className="cal__evlist">
          {selEvents.length === 0 ? (
            <p className="cal__empty">등록된 일정이 없어요.</p>
          ) : (
            selEvents.map((e, idx) => (
              <div key={idx} className="cal__ev">
                <i className={e.type === 'tax' ? 't-tax' : 't-policy'} />
                <div style={{ flex: 1 }}>
                  <b>{e.title}</b>
                  <span>{e.note}</span>
                </div>
                {e.mine && (
                  <button className="cal__ev-del" type="button" onClick={() => delEvent(idx)} aria-label="일정 삭제">✕</button>
                )}
              </div>
            ))
          )}
        </div>
        <form className="cal__add" onSubmit={addEvent}>
          <input type="text" value={ftitle} onChange={(e) => setFtitle(e.target.value)}
            placeholder={`${selLabel}에 일정 추가`} aria-label="일정 제목" />
          <button type="submit">추가</button>
          <div className="cal__add-row">
            <select value={ftype} onChange={(e) => setFtype(e.target.value)} aria-label="분류" style={{ flex: 'none' }}>
              <option value="tax">세금</option>
              <option value="policy">지원사업</option>
            </select>
          </div>
        </form>
        {calErr && <p className="cal__err">{calErr}</p>}
      </div>
    </div>
  );
}

function UpcomingDeadlineCard({ savedPolicies = [], revision = 0 }) {
  // 월말에도 다음 달 초의 D-3 일정을 놓치지 않도록 월 필터 없이 불러온 뒤 화면에서 범위를 자른다.
  const { data: fetched, loading } = useApi(`/calendar?r=${revision}`, NO_EVENTS, eventsByDate);
  const urgentEvents = useMemo(
    () => upcomingCalendarEvents(fetched, savedPolicies),
    [fetched, savedPolicies]
  );

  return (
    <section className="mp-card mp-deadline-card" aria-labelledby="mp-deadline-title">
      <div className="mp-card__head">
        <h2 className="mp-card__title" id="mp-deadline-title">마감 임박 일정</h2>
        <span className="mp-card__tag">D-3 이내</span>
      </div>
      {loading ? (
        <p className="mp-deadline-empty">일정을 확인하고 있어요.</p>
      ) : urgentEvents.length === 0 ? (
        <p className="mp-deadline-empty">3일 이내 마감 일정이 없어요.</p>
      ) : (
        <ul className="mp-deadline-list">
          {urgentEvents.map((item, index) => (
            <li key={`${item.id ?? item.title}-${item.date}-${index}`}>
              <span className={`mp-deadline-kind ${item.type === 'tax' ? 'is-tax' : 'is-policy'}`} aria-hidden="true" />
              <span className="mp-deadline-title" title={item.title}>{item.title}</span>
              <strong className={item.daysLeft === 0 ? 'is-today' : ''}>
                {item.daysLeft === 0 ? 'D-Day' : `D-${item.daysLeft}`}
              </strong>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/* ===== 사업자 유형 진단 ===== */

export function BizTypeDiagnosis() {
  const [rev, setRev] = useState('mid');
  const [taxInvoice, setTaxInvoice] = useState('no');
  const [excluded, setExcluded] = useState('no');

  let vat;
  if (excluded === 'yes' || rev === 'high' || taxInvoice === 'yes') vat = '일반과세자';
  else if (rev === 'low') vat = '간이과세자';
  else vat = '간이과세자 (연 매출 1억 400만 원 미만 유지 시)';
  const corp = rev === 'high'
    ? '법인 전환 검토 — 외부 투자 유치, 대표자 급여 비용화, 낮은 세율 구간 활용에 유리'
    : '개인사업자 유지 — 초기 설립·행정 부담이 작고 폐업도 간단';

  const seg = (val, set, opts) => (
    <div className="seg">
      {opts.map(([v, l]) => (
        <button key={v} type="button" aria-pressed={val === v} onClick={() => set(v)}>{l}</button>
      ))}
    </div>
  );

  return (
    <div className="tool">
      <div className="tool__panel">
        <h2>사업자 유형 진단</h2>
        <div className="field-col">
          <label className="fld"><span>예상 연 매출</span>
            {seg(rev, setRev, [['low', '8천만 원 미만'], ['mid', '8천만 ~ 1.5억'], ['high', '1.5억 초과']])}
          </label>
          <label className="fld"><span>세금계산서 발행이 자주 필요한가요? (B2B 거래)</span>
            {seg(taxInvoice, setTaxInvoice, [['no', '아니오'], ['yes', '예']])}
          </label>
          <label className="fld"><span>간이과세 배제 업종인가요? (변호사·병원·도매 등)</span>
            {seg(excluded, setExcluded, [['no', '아니오'], ['yes', '예']])}
          </label>
        </div>
        <div className="result">
          <p className="result__label">추천 과세 유형</p>
          <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--blue-deep)', margin: '4px 0 6px', letterSpacing: '-0.02em' }}>{vat}</div>
          <p className="result__note"><b>개인 / 법인</b> · {corp}</p>
          <p className="result__note">
            창업 초기에는 개인사업자로 시작하고, 매출·투자 규모가 커지면 법인 전환을 검토하는 흐름이 일반적입니다.
            간이과세자는 세금계산서 발행이 제한되므로 거래처 요구가 많으면 일반과세가 유리합니다.
          </p>
          <p className="result__cite">참고용 안내 · 실제 등록 전 관할 세무서·세무대리인 확인을 권장합니다.</p>
        </div>
      </div>
    </div>
  );
}

/* 서버 정책의 마감일(YYYY-MM-DD) → 남은 일수. 마감일이 없으면 null(상시). */

export function MatchedGov({ user, savedIds, onToggleSave }) {
  const [openGov, setOpenGov] = useState(null);
  const profile = user || { biz: '정보통신업', region: '대전' };
  // Backend: GET /api/policies/recommendations → 프로필 기준 추천 정책 (DB).
  // 저장은 실제 정책 id가 필요하므로 목데이터로 폴백하지 않는다.
  const { data: ranked, loading, source } = useApi('/policies/recommendations?limit=20', null, toPolicies);

  return (
    <div className="tool mg">
      <div className="tool__panel" style={{ marginBottom: 12 }}>
        <h2>AI 추천 공고</h2>
        <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-soft)' }}>
          공고지원 AI가 <b>{profile.biz} · {profile.region}</b> 조건으로 적합한 공고를 골랐어요.
          저장 버튼을 누르면 <b>저장한 공고</b>에 담기고 마감일이 캘린더에 표시됩니다. (저장 {savedIds.size}건)
        </p>
      </div>
      {loading ? (
        <div className="gov__empty">추천 공고를 불러오는 중이에요.</div>
      ) : source !== 'api' ? (
        <div className="gov__empty">추천 공고를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.</div>
      ) : ranked.length === 0 ? (
        <div className="gov__empty">조건에 맞는 추천 공고가 없어요.</div>
      ) : (
        <ul className="gov__list">
          {ranked.map((p) => {
            const dday = policyDday(p.applyEndDate);
            const why = [
              p.region,
              p.industry,
              p.eligible === true && '자격 충족',
              dday !== null && dday >= 0 && dday <= 30 && `마감 D-${dday}`,
            ].filter(Boolean);
            const on = savedIds.has(p.policyId);
            return (
              <li className="gov__card" key={p.policyId}>
                <h3 title={p.title}>{p.title}</h3>
                <span className={'gov__dday' + (dday !== null && dday <= 10 ? ' gov__dday--urgent' : '')}>
                  {policyDdayLabel(dday)}
                </span>
                <p title={p.benefit || ''}>
                  {p.benefit || '공고의 지원 내용을 상세 보기에서 확인해 주세요.'}
                </p>
                <div className="gov__tags">
                  {why.map((w, i) => <span key={i} className="gov__tag">{w}</span>)}
                </div>
                <div className="gov__actions">
                  <button
                    className="gov__action"
                    type="button"
                    onClick={() => setOpenGov({ ...p, why })}
                  >
                    상세 보기
                  </button>
                  <OriginalButton item={p} className="gov__action" />
                  <button
                    className={'gov__action' + (on ? ' gov__action--saved' : '')}
                    type="button"
                    aria-pressed={on}
                    onClick={() => onToggleSave(p)}
                    aria-label={`${p.title} ${on ? '저장 해제' : '저장'}`}
                  >
                    {on ? '★ 저장됨' : '☆ 저장'}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {openGov && (
        <GovDetailModal
          item={openGov}
          saved={savedIds.has(openGov.policyId)}
          saving={false}
          onToggleSave={onToggleSave}
          onClose={() => setOpenGov(null)}
        />
      )}
    </div>
  );
}

/* ===== 저장한 정책 ===== */
/* ===== 공고 · 정책: [저장한 것 | AI 추천 공고] 탭 ===== */

export function SavedGov({ user, savedPolicies, onToggleSave }) {
  const [tab, setTab] = useState('saved');
  const [err, setErr] = useState('');
  const savedIds = new Set(savedPolicies.map((p) => p.policyId));
  const toggle = (item) => {
    setErr('');
    onToggleSave(item).catch(() =>
      setErr('저장 상태를 바꾸지 못했어요. 로그인 상태를 확인하고 다시 시도해 주세요.')
    );
  };
  return (
    <div>
      <div className="mp-tabs" role="tablist" aria-label="공고 · 정책">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'saved'}
          className={'mp-tab' + (tab === 'saved' ? ' is-active' : '')}
          onClick={() => setTab('saved')}
        >
          저장한 공고 {savedPolicies.length}건
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'reco'}
          className={'mp-tab' + (tab === 'reco' ? ' is-active' : '')}
          onClick={() => setTab('reco')}
        >
          AI 추천 공고
        </button>
      </div>
      {err && <p className="cal__err">{err}</p>}
      {tab === 'saved' ? (
        <SavedPolicies savedPolicies={savedPolicies} onToggleSave={toggle} onExplore={() => setTab('reco')} />
      ) : (
        <MatchedGov user={user} savedIds={savedIds} onToggleSave={toggle} />
      )}
    </div>
  );
}

export function SavedPolicies({ savedPolicies, onToggleSave, onExplore }) {
  const [openGov, setOpenGov] = useState(null);
  // 마감일 없는(상시) 정책은 뒤로 보낸다.
  const list = savedPolicies
    .map((p) => ({ p, dday: policyDday(p.applyEndDate) }))
    .sort((a, b) => (a.dday ?? Infinity) - (b.dday ?? Infinity));
  return (
    <div className="tool">
      <div className="tool__panel" style={{ marginBottom: 12 }}>
        <h2>저장한 공고 {list.length}건</h2>
        <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-soft)' }}>
          <b>AI 추천 공고</b>에서 저장한 공고가 모이고, 마감일은 캘린더에도 표시됩니다.
        </p>
      </div>
      {list.length === 0 ? (
        <div className="gov__empty">
          저장한 공고가 없어요.{' '}
          <button type="button" onClick={onExplore} style={linkBtn}>AI 추천 공고 보기</button>
        </div>
      ) : (
        <ul className="gov__list">
          {list.map(({ p, dday }) => (
            <li className="gov__card" key={p.policyId}>
              <h3>{p.title}</h3>
              <span className={'gov__dday' + (dday !== null && dday <= 10 ? ' gov__dday--urgent' : '')}>
                {policyDdayLabel(dday)}
              </span>
              <p>{(p.benefit || '공고의 지원 내용을 상세 보기에서 확인해 주세요.').slice(0, 100)}</p>
              <div className="gov__tags">
                {[p.region, p.industry, p.target].filter(Boolean).map((t, i) => (
                  <span key={i} className="gov__tag">{t.slice(0, 20)}</span>
                ))}
              </div>
              <div className="gov__actions">
                <button
                  className="gov__action"
                  type="button"
                  onClick={() => setOpenGov({ ...p, why: [] })}
                >
                  상세 보기
                </button>
                <OriginalButton item={p} className="gov__action" />
                <button
                  className="gov__action gov__action--saved"
                  type="button"
                  aria-pressed="true"
                  onClick={() => onToggleSave(p)}
                  aria-label={`${p.title} 저장 해제`}
                >
                  ★ 저장됨
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {openGov && (
        <GovDetailModal
          item={openGov}
          saved={savedPolicies.some((p) => p.policyId === openGov.policyId)}
          saving={false}
          onToggleSave={onToggleSave}
          onClose={() => setOpenGov(null)}
        />
      )}
    </div>
  );
}

export function DocsList({ userId, onNavigate, onRequireLogin }) {
  const [draft, setDraft] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [actionError, setActionError] = useState('');
  const [reload, setReload] = useState(0);
  const [pendingActions, setPendingActions] = useState({});
  const [downloadFormats, setDownloadFormats] = useState({});
  const pendingIds = useRef(new Set());

  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    setLoading(true);
    setLoadError('');
    api.bizplanDocuments({ signal: controller.signal }).then((result) => {
      if (alive) {
        setDraft(result.draft);
        setDocuments(result.documents);
      }
    }).catch((error) => {
      if (!alive) return;
      setLoadError(error.status === 401
        ? '서류를 보려면 다시 로그인해 주세요.'
        : '서류 목록을 불러오지 못했습니다. 다시 시도해 주세요.');
      if (error.status === 401) onRequireLogin?.();
    }).finally(() => {
      if (alive) setLoading(false);
    });
    return () => {
      alive = false;
      controller.abort();
    };
  }, [userId, reload, onRequireLogin]);

  const runAction = async (item, action, file) => {
    if (pendingIds.current.has(item.id)) return;
    const isDraft = item.id === 'draft';
    if (action === 'delete' && !window.confirm(isDraft
      ? `“${item.title}” 임시저장 내용을 삭제할까요?`
      : `“${item.title}” 문서와 보관된 모든 형식을 삭제할까요?`)) return;
    pendingIds.current.add(item.id);
    setPendingActions((current) => ({ ...current, [item.id]: action }));
    setActionError('');
    try {
      if (action === 'delete') {
        if (isDraft) {
          await api.deleteBizplanDraft();
          setDraft(null);
          // 이전 브라우저 초안이 다음 방문에 다시 이관되지 않도록 정리한다.
          try { localStorage.removeItem(`changeup:bizplan-draft:${userId}`); } catch { /* 저장소 접근 불가 */ }
        } else {
          await api.deleteBizplanDocument(item.id);
          setDocuments((current) => current.filter((doc) => doc.id !== item.id));
        }
      } else {
        const blob = await api.bizplanDocumentFile(item.id, file.format);
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        try {
          anchor.href = url;
          anchor.download = file.fileName;
          document.body.appendChild(anchor);
          anchor.click();
        } finally {
          anchor.remove();
          URL.revokeObjectURL(url);
        }
      }
    } catch (error) {
      setActionError(error.status === 401
        ? '서류를 이용하려면 다시 로그인해 주세요.'
        : error.status === 404 ? '서류를 찾을 수 없습니다. 목록을 새로고침해 주세요.'
          : `${action === 'delete' ? '삭제' : '다운로드'}하지 못했습니다. 다시 시도해 주세요.`);
      if (error.status === 401) onRequireLogin?.();
    } finally {
      pendingIds.current.delete(item.id);
      setPendingActions((current) => {
        const next = { ...current };
        delete next[item.id];
        return next;
      });
    }
  };

  return (
    <div className="tool">
      <div className="tool__panel">
        <div className="mp-card__head">
          <h2 className="mp-card__title">서류 <span className="mp-card__tag">{loading || loadError ? '' : `저장 문서 ${documents.length}/8`}</span></h2>
          <button type="button" className="mp-card__link" onClick={() => setReload((n) => n + 1)} disabled={loading || Object.keys(pendingActions).length > 0}>새로고침</button>
        </div>
        <p className="mp-basis">임시저장한 내용은 이어서 작성할 수 있어요. 문서는 최대 8개, 파일당 50MiB까지 보관할 수 있어요. 기본 문서는 PDF·HWPX를 선택하고, 제출 양식은 원본 형식으로 다운로드해요.</p>
      </div>
      {actionError && <p className="cal__err" role="alert">{actionError}</p>}
      {loading ? <p className="gov__empty" role="status">서류를 불러오는 중…</p>
        : loadError ? <p className="cal__err" role="alert">{loadError}</p>
          : !draft && documents.length === 0 ? (
            <div className="gov__empty">
              저장한 서류가 없어요.{' '}
              <button type="button" style={linkBtn} onClick={() => onNavigate('bizplan')}>사업계획서 작성하기</button>
            </div>
          ) : (
            <ul className="gov__list">
              {draft && (
                <li className="mp-card" key="draft" style={{ borderColor: 'var(--blue)', background: 'var(--blue-wash)' }}>
                  <div className="mp-card__head">
                    <h3 className="mp-card__title">{draft.title}</h3>
                    <span className="mg__chip">임시저장</span>
                  </div>
                  <p className="mp-basis">작성 중인 사업계획서</p>
                  <p className="mg__meta">마지막 임시저장 · {new Date(draft.updatedAt).toLocaleString('ko-KR')}</p>
                  <div className="gov__actions">
                    <button type="button" className="gov__action" disabled={!!pendingActions.draft} onClick={() => onNavigate('bizplan')}>작성하기</button>
                    <button type="button" className="gov__action" disabled={!!pendingActions.draft} onClick={() => runAction({ id: 'draft', title: draft.title }, 'delete')}>{pendingActions.draft ? '삭제 중…' : '삭제'}</button>
                  </div>
                </li>
              )}
              {documents.map((item) => {
                const file = item.files.find((file) => file.format === downloadFormats[item.id]) || item.files[0];
                return (
                <li className="mp-card" key={item.id}>
                  <div className="mp-card__head">
                    <h3 className="mp-card__title">{item.title}</h3>
                    <span className="mg__chip">저장된 문서</span>
                  </div>
                  <p className="mp-basis" style={{ overflowWrap: 'anywhere', marginTop: 8 }}>{file.fileName}</p>
                  <p className="mg__meta">{file.format.toUpperCase()} · {(file.sizeBytes / (1024 * 1024)).toLocaleString('ko-KR', { maximumFractionDigits: 2 })} MiB · {new Date(item.createdAt).toLocaleString('ko-KR')}</p>
                  <div className="gov__actions">
                    <select aria-label={`${item.title} 다운로드 형식`} value={file.format} disabled={!!pendingActions[item.id]} onChange={(event) => setDownloadFormats((current) => ({ ...current, [item.id]: event.target.value }))}>
                      {item.files.map((file) => <option key={file.format} value={file.format}>{file.format.toUpperCase()}</option>)}
                    </select>
                    <button type="button" className="gov__action" disabled={!!pendingActions[item.id]} onClick={() => runAction(item, 'download', file)}>{pendingActions[item.id] === 'download' ? '다운로드 중…' : '다운로드'}</button>
                    <button type="button" className="gov__action" disabled={!!pendingActions[item.id]} onClick={() => runAction(item, 'delete')}>{pendingActions[item.id] === 'delete' ? '삭제 중…' : '삭제'}</button>
                  </div>
                </li>
                );
              })}
            </ul>
          )}
    </div>
  );
}

/* ===== 구독 · 결제: 결제는 목업(서버가 즉시 승인), 한도는 표시만 한다 ===== */
const won = (n) => `${n.toLocaleString('ko-KR')}원`;
const fmtDate = (v) => (v ? new Date(v).toLocaleDateString('ko-KR') : '—');

export function BillingPanel({ onRequireLogin }) {
  const [sub, setSub] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [confirmPlan, setConfirmPlan] = useState(null);
  const [paying, setPaying] = useState(false);
  const [payError, setPayError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    api.subscription({ signal: controller.signal }).then((result) => {
      if (alive) setSub(result);
    }).catch((error) => {
      if (!alive) return;
      setLoadError(error.status === 401
        ? '구독 정보를 보려면 다시 로그인해 주세요.'
        : '구독 정보를 불러오지 못했습니다. 다시 시도해 주세요.');
      if (error.status === 401) onRequireLogin?.();
    });
    return () => {
      alive = false;
      controller.abort();
    };
  }, [onRequireLogin]);

  useEffect(() => {
    if (!confirmPlan) return undefined;
    const onKey = (e) => e.key === 'Escape' && !paying && setConfirmPlan(null);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [confirmPlan, paying]);

  const pay = async () => {
    setPaying(true);
    setPayError('');
    try {
      const result = await api.changePlan(confirmPlan.key);
      setSub(result);
      setNotice(confirmPlan.price > 0
        ? `${confirmPlan.name} 플랜 결제가 완료되었어요.`
        : '구독이 해지되어 무료 플랜으로 변경되었어요.');
      setConfirmPlan(null);
    } catch (error) {
      setPayError(error.status === 401
        ? '다시 로그인해 주세요.'
        : '결제를 처리하지 못했습니다. 다시 시도해 주세요.');
      if (error.status === 401) onRequireLogin?.();
    } finally {
      setPaying(false);
    }
  };

  if (loadError) return <p className="cal__err" role="alert">{loadError}</p>;
  if (!sub) return <p className="gov__empty" role="status">구독 정보를 불러오는 중…</p>;

  const current = sub.plans.find((p) => p.key === sub.current.plan) || sub.plans[0];
  const { policyChat, policyChatLimit, taxChat } = sub.usage;
  const policyPct = policyChatLimit ? Math.min(100, Math.round((policyChat / policyChatLimit) * 100)) : 0;
  const isPaid = current.price > 0;

  return (
    <div className="bill">
      {notice && <p className="bill__notice" role="status">{notice}</p>}
      <div className="bill__top">
        <section className="mp-card">
          <div className="mp-card__head">
            <h2 className="mp-card__title">현재 플랜</h2>
            <span className="mg__chip">{isPaid ? '구독 중' : '무료'}</span>
          </div>
          <p className="mp-pct">{current.name}</p>
          <dl className="bill__meta">
            <div><dt>월 요금</dt><dd className="u-num">{won(current.price)}</dd></div>
            <div><dt>이용 시작</dt><dd className="u-num">{fmtDate(sub.current.startedAt)}</dd></div>
            <div><dt>다음 결제일</dt><dd className="u-num">{fmtDate(sub.current.renewsAt)}</dd></div>
          </dl>
        </section>
        <section className="mp-card">
          <div className="mp-card__head">
            <h2 className="mp-card__title">이번 달 사용량</h2>
          </div>
          <div className="bill__usage">
            <span>공고지원 AI 상담</span>
            <b className="u-num">{policyChat}{policyChatLimit ? ` / ${policyChatLimit}회` : '회 · 무제한'}</b>
          </div>
          {policyChatLimit && (
            <div className="mp-bar"><i className={policyChat >= policyChatLimit ? 'is-full' : ''} style={{ width: policyPct + '%' }} /></div>
          )}
          <div className="bill__usage">
            <span>세무 Assistant 상담</span>
            <b className="u-num">{taxChat}회 · 무제한</b>
          </div>
        </section>
      </div>

      <div className="bill__plans">
        {sub.plans.map((plan) => {
          const isCurrent = plan.key === current.key;
          return (
            <section key={plan.key} className={'mp-card bill__plan' + (isCurrent ? ' is-current' : '')}>
              <h3 className="mp-card__title">{plan.name}</h3>
              <p className="bill__price"><b className="u-num">{won(plan.price)}</b><span> / 월</span></p>
              <ul className="bill__features">
                {plan.features.map((f) => (
                  <li key={f.label} className={f.value === false ? 'is-off' : ''}>
                    <span>{f.label}</span>
                    <b>{f.value === true ? 'O' : f.value === false ? '—' : f.value}</b>
                  </li>
                ))}
              </ul>
              <button
                type="button"
                className={'btn ' + (isCurrent ? 'btn--ghost' : 'btn--primary')}
                disabled={isCurrent}
                onClick={() => { setPayError(''); setNotice(''); setConfirmPlan(plan); }}
              >
                {isCurrent ? '이용 중' : plan.price === 0 ? '무료로 변경' : `${plan.name} 결제하기`}
              </button>
            </section>
          );
        })}
      </div>
      <p className="mp-basis">결제는 모의 결제로 실제 청구가 발생하지 않아요. 한도는 안내용이며 기능 이용을 제한하지 않아요.</p>

      {confirmPlan && (
        <div className="bill__overlay" onMouseDown={(e) => e.target === e.currentTarget && !paying && setConfirmPlan(null)}>
          <div className="bill__dialog" role="dialog" aria-modal="true" aria-labelledby="bill-dialog-title">
            <h2 id="bill-dialog-title" className="mp-card__title">
              {confirmPlan.price > 0 ? `${confirmPlan.name} 플랜 결제` : '구독 해지'}
            </h2>
            {confirmPlan.price > 0 ? (
              <p className="mp-basis">
                매월 <b>{won(confirmPlan.price)}</b>이 결제되고, 다음 결제일은 한 달 뒤예요.
                <br />모의 결제로 실제 청구는 발생하지 않아요.
              </p>
            ) : (
              <p className="mp-basis">{current.name} 구독을 해지하고 무료 플랜으로 바로 변경할까요?</p>
            )}
            {payError && <p className="cal__err" role="alert">{payError}</p>}
            <div className="bill__actions">
              <button type="button" className="btn btn--ghost" disabled={paying} onClick={() => setConfirmPlan(null)}>취소</button>
              <button type="button" className="btn btn--primary" disabled={paying} onClick={pay}>
                {paying ? '처리 중…' : confirmPlan.price > 0 ? `${won(confirmPlan.price)} 결제` : '해지하기'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ===== 상담 기록: 화면(카테고리)별로 나눠 보여 준다 ===== */
// 각 상담 화면이 대화를 저장할 때 쓰는 category 와 같아야 한다

export function ChatLog({ user }) {
  const [tab, setTab] = useState('tax');
  const [logs, setLogs] = useState({ roadmap: [], tax: [], policy: [] });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const userId = user && user.id;

  useEffect(() => {
    if (!userId) return;
    let alive = true;
    setBusy(true);
    setErr('');
    // 탭마다 따로 부르면 전환이 느려서, 세 화면 기록을 한 번에 받아 둔다
    Promise.all(CHATLOG_TABS.map((t) => api.chatHistory(t.key).catch(() => null)))
      .then((res) => {
        if (!alive) return;
        const next = {};
        CHATLOG_TABS.forEach((t, i) => {
          next[t.key] = (res[i] && res[i].messages) || [];
        });
        setLogs(next);
        if (res.every((r) => r === null)) setErr('상담 기록을 불러오지 못했어요.');
      })
      .finally(() => {
        if (alive) setBusy(false);
      });
    return () => {
      alive = false;
    };
  }, [userId]);

  const rows = logs[tab] || [];

  return (
    <div className="tool">
      <div className="tool__panel">
        <h2>상담 기록</h2>
        {!userId ? (
          <p className="cvx__empty">로그인하면 저장된 상담 기록을 볼 수 있어요.</p>
        ) : (
          <React.Fragment>
            <div className="mp-tabs" role="tablist" aria-label="상담 기록 분류">
              {CHATLOG_TABS.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  role="tab"
                  aria-selected={tab === t.key}
                  className={'mp-tab' + (tab === t.key ? ' is-active' : '')}
                  onClick={() => setTab(t.key)}
                >
                  {t.label} {(logs[t.key] || []).length}건
                </button>
              ))}
            </div>
            {busy ? (
              <p className="cvx__empty">기록을 불러오는 중…</p>
            ) : err ? (
              <p className="ai__err">{err}</p>
            ) : rows.length === 0 ? (
              <p className="cvx__empty">이 화면에서 주고받은 상담 기록이 아직 없어요.</p>
            ) : (
              <ul className="clog">
                {rows
                  .slice()
                  .reverse()
                  .map((row) => (
                    <li key={row.id} className="clog__item">
                      <p className="clog__q">{row.question}</p>
                      <p className="clog__a">{row.answer}</p>
                      {row.created_at && (
                        <span className="clog__at">{String(row.created_at).slice(0, 10)}</span>
                      )}
                    </li>
                  ))}
              </ul>
            )}
          </React.Fragment>
        )}
      </div>
    </div>
  );
}

/* ===== 사업자 정보 / 설정 (only='profile' | 'notif') ===== */
// REGIONS 는 users.region 의 CHECK 제약(DB/app_extras.sql)이 허용하는 17개 시·도와 같다.

export function ProfileSettings({ user, only, onSaved }) {
  const [form, setForm] = useState({
    name: user.name,
    email: user.email || '',
    biz: user.biz || '',
    region: user.region || '',
    age: user.age ? String(user.age) : '',
  });
  const [notif, setNotif] = useState({ tax: true, deadline: true, news: false });
  const [savedMsg, setSavedMsg] = useState('');
  const upd = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const save = async (e) => {
    e.preventDefault();
    // 개인정보(PUT /users/me)와 사업자 정보(PUT /users/me/business-profile)는 저장 경로가 다르다.
    // 회원가입(LoginModal.authenticate)과 같은 쌍으로 보낸다.
    const patch = { name: form.name };
    if (form.region) patch.region = form.region;
    if (form.age !== '') {
      const n = Number(form.age);
      if (!Number.isFinite(n) || n < 15 || n > 120) {
        setSavedMsg('대표자 연령을 만 나이로 입력해 주세요.');
        setTimeout(() => setSavedMsg(''), 2500);
        return;
      }
      patch.age = n;
    }
    try {
      await api.updateMe(patch);
      await api.updateBusinessProfile({ industry: form.biz });
      const updatedUser = await api.currentUser();
      if (!updatedUser) throw new Error('사용자 정보를 조회하지 못했습니다.');
      if (onSaved) onSaved(updatedUser);
      setSavedMsg('저장되었습니다.');
    } catch {
      setSavedMsg('저장하지 못했습니다. 잠시 후 다시 시도해 주세요.');
    }
    setTimeout(() => setSavedMsg(''), 2500);
  };
  const showProfile = only !== 'notif';
  const showNotif = only !== 'profile';
  return (
    <div className="tool">
      {showProfile && (
      <form className="tool__panel" onSubmit={save} style={{ marginBottom: 12 }}>
        <h2>사업자 정보</h2>
        <div className="field-col">
          <label className="fld"><span>이름</span><input style={inputStyle} value={form.name} onChange={upd('name')} /></label>
          <label className="fld"><span>이메일</span><input style={inputStyle} type="email" value={form.email} onChange={upd('email')} /></label>
          <label className="fld"><span>업종</span>
            <select style={inputStyle} value={form.biz} onChange={upd('biz')} required>
              <option value="" disabled>업종을 선택해 주세요</option>
              {form.biz && !INDUSTRIES.includes(form.biz) && <option value={form.biz}>{form.biz}</option>}
              {INDUSTRIES.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </label>
          <label className="fld"><span>사업장 지역</span>
            <select style={inputStyle} value={form.region} onChange={upd('region')} required>
              <option value="" disabled>지역을 선택해 주세요</option>
              {form.region && !REGIONS.includes(form.region) && <option value={form.region}>{form.region}</option>}
              {REGIONS.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </label>
          <label className="fld"><span>대표자 연령 (만 나이)</span>
            <input style={inputStyle} type="number" inputMode="numeric" min="15" max="120"
              value={form.age} onChange={upd('age')} placeholder="예: 32" />
          </label>
        </div>
        <button type="submit" style={{
          marginTop: 14, padding: '10px 20px', border: 0, borderRadius: 11,
          background: 'linear-gradient(135deg, var(--blue), var(--blue-deep))', color: '#fff',
          fontSize: 13.5, fontWeight: 700, cursor: 'pointer',
        }}>저장</button>
        {savedMsg && <p className="pf-saved">{savedMsg}</p>}
      </form>
      )}
      {showNotif && (
      <div className="tool__panel">
        <h2>알림 설정</h2>
        {[['tax', '세금 신고 마감 알림'], ['deadline', '관심 공고 마감 3일 전 알림'], ['news', '창업 뉴스레터']].map(([k, label]) => (
          <div className="pf-toggle" key={k}>
            <span>{label}</span>
            <button type="button" className="pf-switch" aria-pressed={notif[k]} aria-label={label}
              onClick={() => setNotif((p) => ({ ...p, [k]: !p[k] }))} />
          </div>
        ))}
      </div>
      )}
    </div>
  );
}

// 사업계획서 보관함: 만든 사업계획서를 최근 저장 순으로 보여주고, 이어서 작성·이름 변경·삭제·새로 만들기를 한다.
// 열기와 새로 만들기는 서버에서 작성 화면 임시저장을 바꾼 뒤 사업계획서 페이지로 이동한다.
const BP_STATUS_STEPS = ['writing', 'drafted', 'evaluated', 'done'];

function formatPlanDate(value) {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

export function BizplanManager({ onOpenBizplan }) {
  const [plans, setPlans] = useState(null);
  const [err, setErr] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [renameId, setRenameId] = useState(null);
  const [renameDraft, setRenameDraft] = useState('');

  const load = () => {
    setErr('');
    api.bizplanPlans()
      .then((r) => setPlans((r && r.plans) || []))
      .catch(() => {
        setPlans([]);
        setErr('사업계획서 목록을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.');
      });
  };
  useEffect(load, []);

  const run = async (id, action, failMsg) => {
    if (busyId !== null) return;
    setBusyId(id);
    setErr('');
    try {
      await action();
    } catch (e) {
      setErr(failMsg);
      setBusyId(null);
      return;
    }
    setBusyId(null);
  };

  const open = (p) => run(p.id, async () => {
    await api.openBizplanPlan(p.id);
    onOpenBizplan && onOpenBizplan();
  }, '사업계획서를 열지 못했어요. 잠시 후 다시 시도해 주세요.');

  const create = () => run('new', async () => {
    await api.newBizplanPlan();
    onOpenBizplan && onOpenBizplan();
  }, '새 사업계획서를 시작하지 못했어요. 잠시 후 다시 시도해 주세요.');

  const remove = (p) => {
    if (!window.confirm(`'${p.title}'을(를) 삭제할까요? 삭제하면 되돌릴 수 없어요.`)) return;
    run(p.id, async () => {
      await api.deleteBizplanPlan(p.id);
      setPlans((cur) => cur.filter((x) => x.id !== p.id));
    }, '삭제하지 못했어요. 잠시 후 다시 시도해 주세요.');
  };

  const saveRename = (p) => {
    const title = renameDraft.trim();
    if (!title || title === p.title) {
      setRenameId(null);
      return;
    }
    run(p.id, async () => {
      await api.renameBizplanPlan(p.id, title);
      setPlans((cur) => cur.map((x) => (x.id === p.id ? { ...x, title } : x)));
      setRenameId(null);
    }, '이름을 바꾸지 못했어요. 잠시 후 다시 시도해 주세요.');
  };

  return (
    <div className="tool mp-bp">
      <div className="tool__panel">
        <div className="mp-bp__head">
          <div>
            <h2 className="mp-bp__title">내 사업계획서</h2>
            <p className="mp-bp__sub">
              사업계획서 페이지에서 임시저장하거나 초안·평가가 나오면 여기에 자동으로 모여요.
            </p>
          </div>
          <button type="button" className="mp-bp__new" onClick={create} disabled={busyId !== null}>
            + 새 사업계획서
          </button>
        </div>
        {err && <p className="cal__err">{err}</p>}

        {plans === null ? (
          <p className="ai__hint">불러오는 중…</p>
        ) : plans.length === 0 ? (
          <div className="mp-bp__empty">
            <p>아직 만든 사업계획서가 없어요.</p>
            <button type="button" className="mp-bp__new" onClick={create} disabled={busyId !== null}>
              첫 사업계획서 만들기
            </button>
          </div>
        ) : (
          <ul className="mp-bp__list">
            {plans.map((p) => {
              const stepIdx = Math.max(0, BP_STATUS_STEPS.indexOf(p.status));
              const busy = busyId === p.id;
              return (
                <li key={p.id} className={'mp-bp__item' + (p.isCurrent ? ' is-current' : '')}>
                  <div className="mp-bp__main">
                    <div className="mp-bp__line1">
                      {renameId === p.id ? (
                        <form className="mp-bp__rename" onSubmit={(e) => { e.preventDefault(); saveRename(p); }}>
                          <input type="text" value={renameDraft} maxLength={200} autoFocus aria-label="사업계획서 이름"
                            onChange={(e) => setRenameDraft(e.target.value)}
                            onKeyDown={(e) => e.key === 'Escape' && setRenameId(null)} />
                          <button type="submit" disabled={busy || !renameDraft.trim()}>저장</button>
                          <button type="button" onClick={() => setRenameId(null)} disabled={busy}>취소</button>
                        </form>
                      ) : (
                        <h3 className="mp-bp__name" title={p.title}>{p.title}</h3>
                      )}
                      {p.isCurrent && <span className="mp-bp__current">작성 화면에 열려 있음</span>}
                    </div>
                    <div className="mp-bp__meta">
                      <span className={'mp-bp__status mp-bp__status--' + p.status}>{p.statusLabel}</span>
                      {p.score != null && <span className="mp-bp__score u-num">평가 {p.score}점</span>}
                      <span className="mp-bp__date">마지막 저장 {formatPlanDate(p.updatedAt)}</span>
                    </div>
                    <ol className="mp-bp__progress" aria-label={`진행 단계: ${p.statusLabel}`}>
                      {['작성', '초안', '평가', '완성'].map((label, i) => (
                        <li key={label} className={i <= stepIdx ? 'is-on' : ''}>{label}</li>
                      ))}
                    </ol>
                  </div>
                  <div className="mp-bp__actions">
                    <button type="button" className="mp-bp__open" onClick={() => open(p)} disabled={busyId !== null}>
                      {busy ? '여는 중…' : p.status === 'done' ? '열기 · 다운로드' : '이어서 작성'}
                    </button>
                    <button type="button" className="mp-bp__btn" disabled={busyId !== null}
                      onClick={() => { setRenameId(p.id); setRenameDraft(p.title); }}>
                      이름 변경
                    </button>
                    <button type="button" className="mp-bp__btn mp-bp__btn--danger" onClick={() => remove(p)}
                      disabled={busyId !== null}>
                      삭제
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

export function MyPage({ user, onHome, onLogout, onNavigate, onLoginClick, onRequireLogin, roadmapDone = {}, savedPolicies = [], onToggleSavedPolicy, onOpenRoadmap, onOpenTax, onOpenGov, onProfileSaved }) {
  const [siteMenuOpen, setSiteMenuOpen] = useState(false);
  const [menu, setMenu] = useState('home');
  const [calendarRevision, setCalendarRevision] = useState(0);
  const activeLabel = (MP_MENU.find((m) => m.key === menu) || {}).label || '';

  // 대시보드 카드에 실제 상담 기록을 띄운다 (화면별 최근 질문 MP_RECENT_MAX 개)
  const [recentQ, setRecentQ] = useState({ tax: [], policy: [] });
  const mpUserId = user && user.id;
  useEffect(() => {
    if (!mpUserId) {
      setRecentQ({ tax: [], policy: [] });
      return undefined;
    }
    let alive = true;
    Promise.all([
      api.chatHistory('tax').catch(() => null),
      api.chatHistory('policy').catch(() => null),
    ]).then(([t, p]) => {
      if (!alive) return;
      // 서버는 오래된 순으로 준다 → 뒤에서 잘라 최신순으로 뒤집는다
      const pick = (r) =>
        ((r && r.messages) || []).slice(-MP_RECENT_MAX).reverse().map((m) => m.question);
      setRecentQ({ tax: pick(t), policy: pick(p) });
    });
    return () => {
      alive = false;
    };
  }, [mpUserId]);

  // 창업 로드맵 진행률 (로드맵 페이지와 공유되는 roadmapDone 기반)
  const rmStepDone = (k) => {
    const t = ROADMAP_TASKS[k] || [];
    return t.length > 0 && t.every((_, i) => roadmapDone[`${k}:${i}`]);
  };
  const rmTotal = ROADMAP.reduce((n, s) => n + (ROADMAP_TASKS[s.k] || []).length, 0);
  const rmDoneCount = Object.values(roadmapDone).filter(Boolean).length;
  const rmPct = rmTotal ? Math.round((rmDoneCount / rmTotal) * 100) : 0;
  const rmStepsDone = ROADMAP.filter((s) => rmStepDone(s.k)).length;
  const rmCurrent = ROADMAP.find((s) => !rmStepDone(s.k)) || ROADMAP[ROADMAP.length - 1];

  return (
    <div className="mp">
      <aside className="mp-side">
        <button className="mp-brand" type="button" onClick={onHome}>
          <LogoMark />
          <BrandWord />
        </button>
        <nav className="mp-nav" aria-label="마이페이지 메뉴">
          {MP_MENU.map((m, i) => {
            if (m.group) return <div className="mp-group" key={`g-${i}`}>{m.group}</div>;
            if (m.divider) return <div className="mp-side__div" key={`d-${i}`} />;
            return (
              <button
                key={m.key}
                type="button"
                className={
                  'mp-link' +
                  (m.sub ? ' mp-link--sub' : '') +
                  (menu === m.key ? ' mp-link--active' : '')
                }
                aria-current={menu === m.key ? 'page' : undefined}
                onClick={() => setMenu(m.key)}
              >
                <span>{m.label}</span>
                {m.tag && <span className="mp-tag">{m.tag}</span>}
              </button>
            );
          })}
        </nav>
      </aside>

      <main className={'mp-main' + (menu === 'home' ? ' mp-main--dash' : '')}>
        <div className="mp-head">
          <div>
            <h1 className="mp-hello">안녕하세요, {user.name}님</h1>
            <p className="mp-basis">사업자 정보 기준 · {user.biz} · {user.region}</p>
          </div>
          <div className="mp-head__actions">
            <button className="mp-logout" type="button" onClick={onLogout}>로그아웃</button>
            <button
              className="hamburger"
              type="button"
              aria-haspopup="dialog"
              aria-expanded={siteMenuOpen}
              aria-label="메뉴 열기"
              onClick={() => setSiteMenuOpen(true)}
            >
              <span /><span /><span />
            </button>
          </div>
        </div>
        <MenuDrawer
          open={siteMenuOpen}
          onClose={() => setSiteMenuOpen(false)}
          onNavigate={onNavigate}
          user={user}
          onAuth={onLoginClick}
        />

        {menu === 'home' ? (
          <div className="mp-dash">
            <div className="mp-grid">
            <section
              className="mp-card mp-card--action"
              role="button"
              tabIndex={0}
              onClick={onOpenRoadmap}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onOpenRoadmap && onOpenRoadmap();
                }
              }}
            >
              <div className="mp-card__head">
                <h2 className="mp-card__title">창업 로드맵 진행률</h2>
                <span className="mp-card__tag">{rmStepsDone} / {ROADMAP.length}단계</span>
              </div>
              <p className="mp-pct u-num">{rmPct}%</p>
              <div className="mp-bar"><i style={{ width: rmPct + '%' }} /></div>
              <p className="mp-cite">
                <span>{rmPct === 100 ? '완료' : '현재 단계'}</span>
                <span>{rmCurrent.k}. <b>{rmCurrent.t}</b></span>
              </p>
            </section>

            <UpcomingDeadlineCard savedPolicies={savedPolicies} revision={calendarRevision} />

            <section
              className="mp-card mp-card--action"
              role="button"
              tabIndex={0}
              onClick={onOpenTax}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onOpenTax && onOpenTax();
                }
              }}
            >
              <div className="mp-card__head">
                <h2 className="mp-card__title">세무 AI Assistant</h2>
                <span className="mp-card__link">세무 AI ›</span>
              </div>
              <p className="mp-recap">최근 질문</p>
              <ul className="mp-rows mp-rows--recap">
                {recentQ.tax.length === 0 ? (
                  <li><span className="mp-consult mp-consult--none">아직 상담 기록이 없어요.</span></li>
                ) : (
                  recentQ.tax.map((q, i) => (
                    <li key={i}><span className="mp-consult" title={q}>{q}</span></li>
                  ))
                )}
              </ul>
            </section>

            <section
              className="mp-card mp-card--action"
              role="button"
              tabIndex={0}
              onClick={onOpenGov}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onOpenGov && onOpenGov();
                }
              }}
            >
              <div className="mp-card__head">
                <h2 className="mp-card__title">공고지원 AI</h2>
                <span className="mp-card__link">공고지원 AI ›</span>
              </div>
              <p className="mp-recap">최근 질문 · 저장 {savedPolicies.length}건</p>
              <ul className="mp-rows mp-rows--recap">
                {recentQ.policy.length === 0 ? (
                  <li><span className="mp-consult mp-consult--none">아직 상담 기록이 없어요.</span></li>
                ) : (
                  recentQ.policy.map((q, i) => (
                    <li key={i}><span className="mp-consult" title={q}>{q}</span></li>
                  ))
                )}
              </ul>
            </section>

            </div>
            <MpCalendar
              savedPolicies={savedPolicies}
              onEventsChanged={() => setCalendarRevision((n) => n + 1)}
            />
          </div>
        ) : menu === 'profile' ? (
          <ProfileSettings user={user} only="profile" onSaved={onProfileSaved} />
        ) : menu === 'billing' ? (
          <BillingPanel key={mpUserId} onRequireLogin={onRequireLogin} />
        ) : menu === 'saved' ? (
          <SavedGov user={user} savedPolicies={savedPolicies} onToggleSave={onToggleSavedPolicy} />
        ) : menu === 'docs' ? (
          <DocsList key={mpUserId} userId={mpUserId} onNavigate={onNavigate} onRequireLogin={onRequireLogin} />
        ) : menu === 'bizplans' ? (
          <BizplanManager onOpenBizplan={() => onNavigate && onNavigate('bizplan')} />
        ) : menu === 'settings' ? (
          <ProfileSettings user={user} only="notif" />
        ) : (
          <div className="mp-stub">
            <b>{activeLabel}</b> 화면은 준비 중입니다.
          </div>
        )}
      </main>
    </div>
  );
}

/* ---------- 상단 내비 ---------- */
