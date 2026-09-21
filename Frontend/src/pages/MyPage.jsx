import React, { useState, useEffect, useMemo } from 'react';
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

/* ===== 지출관리: 영수증 업로드 → OCR → 경비 인정 판정 ===== */

const EXP_JUDGE_CATS = ['사무용품', '통신비', '차량유지비', '광고선전비', '임차료', '복리후생비', '접대비', '교육·도서', '기타'];
// 목록 카드는 폭이 좁아 서버가 주는 긴 tierLabel("애매함 (확인 필요)") 대신 짧은 표기를 쓴다.
const TIER_SHORT_LABELS = { high: '높음', ambiguous: '애매함', low: '어려움' };

// 서버는 UTC 시각을 주므로 브라우저 현지 시각(한국이면 KST)으로 바꿔 "9월 20일 오후 9:39"처럼 보여준다.
function formatUploadedAt(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const sameYear = d.getFullYear() === new Date().getFullYear();
  return d.toLocaleString('ko-KR', {
    ...(sameYear ? {} : { year: 'numeric' }),
    month: 'long',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

const STEP_ICONS = { pass: '✔', warn: '!', fail: '✖', unknown: '?' };

// 길어지기 쉬운 상세 내용을 제목 줄만 남기고 접었다 펼 수 있게 한다.
function Fold({ title, hint, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className={'exp-fold' + (open ? ' is-open' : '')}>
      <button type="button" className="exp-fold__head" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span className="exp-fold__ttl">{title}</span>
        {hint && <span className="exp-fold__hint">{hint}</span>}
        <span className="exp-fold__chev" aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>
      {open && <div className="exp-fold__body">{children}</div>}
    </section>
  );
}

// 영수증에서 읽은 항목(원문 인용 포함). 못 읽은 항목은 빨간색으로 드러낸다.
function ReceiptFields({ analysis }) {
  return (
    <React.Fragment>
      {analysis.ocrSource === 'mock' && (
        <p className="cal__err">사진을 읽지 못해 아래는 실제 영수증 값이 아닌 샘플이에요. 다시 올려 주세요.</p>
      )}
      <ul className="exp-ana__fields">
        {analysis.fields.map((f) => {
          const state = f.read === false ? 'miss' : f.read ? 'ok' : 'unk';
          return (
            <li key={f.key} className={'exp-ana__field is-' + state}>
              <span className="exp-ana__mark" aria-hidden="true">{state === 'miss' ? '✖' : state === 'ok' ? '✔' : '?'}</span>
              <span className="exp-ana__lbl">{f.label}</span>
              <span className="exp-ana__val">
                {f.value || '인식 못 함'}
                {state === 'unk' && <small> (기록 이전 영수증)</small>}
              </span>
              {f.evidence && (
                <span className="exp-ana__quote" title="영수증에 인쇄된 원문">
                  영수증 원문 “{f.evidence}”
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </React.Fragment>
  );
}

// 읽은 내용으로 판정에 이른 단계를 진행선으로 보여준다.
function ReceiptSteps({ analysis }) {
  return (
    <ol className="exp-ana__steps">
      {analysis.steps.map((st) => (
        <li key={st.key} className={'exp-ana__step is-' + st.result}>
          <span className="exp-ana__dot" aria-hidden="true">{STEP_ICONS[st.result] || '?'}</span>
          <div>
            <b>{st.title}</b>
            <p>{st.detail}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

// 지출항목과 증빙 상태에 맞는 관련 법령. 조문을 누르면 국가법령정보센터 원문으로 이동한다.
function LawList({ laws, note }) {
  return (
    <React.Fragment>
      {note && <p className="exp-law__note">{note}</p>}
      <ul className="exp-law">
        {laws.map((l) => (
          <li key={l.law + l.article} className="exp-law__item">
            <a href={l.url} target="_blank" rel="noreferrer">
              <b>{l.law} {l.article}</b>
              <span>{l.title}</span>
              {l.who && <em>{l.who}</em>}
              <i aria-hidden="true">↗</i>
            </a>
            <p>{l.point}</p>
          </li>
        ))}
      </ul>
      <p className="exp-law__disc">법령 요지는 이해를 돕기 위한 요약이에요. 정확한 내용은 원문과 세무사 확인이 필요해요.</p>
    </React.Fragment>
  );
}

// 카드를 펼치면 근거(RAG 출처 포함)를 그때 불러온다 — 목록 조회 때마다 매번 LLM을 부르지 않기 위해서다.
function ReceiptCard({ item, onDeleted, onCategoryChanged }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [imgUrl, setImgUrl] = useState(null);
  const [zoom, setZoom] = useState(false);
  const [analysis, setAnalysis] = useState(null); // 무엇을 읽고 어떻게 판단했는지 (LLM 없이 바로 온다)
  const [anaFailed, setAnaFailed] = useState(false);
  const [catBusy, setCatBusy] = useState(false);
  const [catErr, setCatErr] = useState('');
  const [catOpen, setCatOpen] = useState(false);
  const catListRef = React.useRef(null);
  const catWrapRef = React.useRef(null);

  // 펼쳐진 목록 밖을 누르거나 Esc를 누르면 닫는다.
  useEffect(() => {
    if (!catOpen) return undefined;
    const onDown = (e) => {
      if (catWrapRef.current && !catWrapRef.current.contains(e.target)) setCatOpen(false);
    };
    const onKey = (e) => e.key === 'Escape' && setCatOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [catOpen]);

  // 열릴 때 현재 항목이 목록 안에서 보이도록 스크롤한다(페이지 스크롤은 건드리지 않는다).
  useEffect(() => {
    const box = catListRef.current;
    const on = box && box.querySelector('.is-on');
    if (catOpen && box && on) box.scrollTop = Math.max(0, on.offsetTop - box.clientHeight / 2 + on.offsetHeight / 2);
  }, [catOpen]);

  const loadAnalysis = () =>
    api
      .expenseAnalysis(item.expenseId)
      .then((a) => {
        setAnalysis(a);
        setAnaFailed(false);
      })
      .catch(() => setAnaFailed(true));

  useEffect(() => {
    if (!zoom) return undefined;
    const onKey = (e) => e.key === 'Escape' && setZoom(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [zoom]);

  // 목록에 뜨자마자 내가 올린 영수증이 맞는지 썸네일로 보여준다.
  useEffect(() => {
    let alive = true;
    let objUrl = null;
    api
      .receiptImage(item.receiptId)
      .then((blob) => {
        if (!alive) return;
        objUrl = URL.createObjectURL(blob);
        setImgUrl(objUrl);
      })
      .catch(() => {
        /* 원본이 없어도(예: 목업 응답) 목록은 그대로 보여준다 */
      });
    return () => {
      alive = false;
      if (objUrl) URL.revokeObjectURL(objUrl);
    };
  }, [item.receiptId]);

  const openDetail = async () => {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (!analysis) loadAnalysis();
    if (detail || busy) return;
    setBusy(true);
    setErr('');
    try {
      setDetail(await api.expenseDeductibility(item.expenseId));
    } catch (e) {
      setErr('근거를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setBusy(false);
    }
  };

  const changeCategory = async (category) => {
    setCatOpen(false);
    if (catBusy || category === item.category) return;
    setCatBusy(true);
    setCatErr('');
    try {
      const d = await api.updateExpenseCategory(item.expenseId, category);
      setDetail(d);
      loadAnalysis();
      onCategoryChanged(item.expenseId, category, d);
    } catch (e2) {
      setCatErr('지출항목을 바꾸지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setCatBusy(false);
    }
  };

  const remove = async () => {
    if (!window.confirm('이 영수증과 지출 기록을 삭제할까요?')) return;
    try {
      await api.deleteExpense(item.expenseId);
      onDeleted(item.expenseId);
    } catch (e) {
      setErr('삭제하지 못했어요. 잠시 후 다시 시도해 주세요.');
    }
  };

  const tierCls = item.tier === 'high' ? 'ok' : item.tier === 'low' ? 'bad' : 'check';
  const uploadedLabel = formatUploadedAt(item.uploadedAt);

  return (
    <li className="exp-card">
      <div className="exp-card__main">
        <button
          type="button"
          className="exp-card__thumb"
          onClick={() => imgUrl && setZoom(true)}
          disabled={!imgUrl}
          aria-label="영수증 원본 크게 보기"
        >
          {imgUrl ? (
            <React.Fragment>
              <img src={imgUrl} alt={`${item.vendor} 영수증`} />
              <span className="exp-card__zoomhint" aria-hidden="true">🔍 크게 보기</span>
            </React.Fragment>
          ) : (
            <span className="exp-card__thumb-ph">
              🧾
              <small>원본 없음</small>
            </span>
          )}
        </button>

        <div className="exp-card__info">
          <button type="button" className="exp-card__head" onClick={openDetail} aria-expanded={open}>
            <span className="exp-card__title">
              <span className="exp-card__vendor">{item.vendor}</span>
              {uploadedLabel && (
                <span className="exp-card__uploaded" title="영수증을 올린 시각">
                  🕒 {uploadedLabel} 업로드
                </span>
              )}
            </span>
            <span className="u-num exp-card__amount">{item.amount.toLocaleString()}원</span>
          </button>
          <div className="exp-card__catrow">
            <span className="exp-card__catlabel">지출항목</span>
            <span className={'exp-ded exp-ded--' + tierCls} title={item.tierLabel}>
              경비 인정 {TIER_SHORT_LABELS[item.tier] || item.tierLabel}
            </span>
          </div>
          <div className="exp-dd" ref={catWrapRef}>
            <button
              type="button"
              className={'exp-dd__btn' + (catOpen ? ' is-open' : '')}
              onClick={() => setCatOpen((v) => !v)}
              disabled={catBusy}
              aria-haspopup="listbox"
              aria-expanded={catOpen}
              aria-label={`지출항목: ${item.category}. 눌러서 바꾸기`}
            >
              <span>{item.category}</span>
              <span className="exp-dd__chev" aria-hidden="true">{catOpen ? '▴' : '▾'}</span>
            </button>
            {catOpen && (
              <div className="exp-dd__list" role="listbox" aria-label="지출항목" ref={catListRef}>
                {EXP_JUDGE_CATS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    role="option"
                    aria-selected={item.category === c}
                    className={'exp-dd__opt' + (item.category === c ? ' is-on' : '')}
                    onClick={() => changeCategory(c)}
                  >
                    {c}
                    {item.category === c && <span aria-hidden="true">✔</span>}
                  </button>
                ))}
              </div>
            )}
          </div>
          {catBusy && <p className="exp-card__busy" role="status">지출항목을 바꾸고 판정을 다시 계산하고 있어요…</p>}
          {catErr && <p className="cal__err">{catErr}</p>}
          <div className="exp-card__tags">
            <span className="exp-cat">{item.proofTypeLabel}</span>
            {item.proofValid === false && <span className="exp-cat exp-cat--warn">증빙 부적격</span>}
            {item.proofValid === null && <span className="exp-cat exp-cat--warn">증빙 확인 필요</span>}
            {(item.missingFields || []).map((m) => (
              <span key={m} className="exp-cat exp-cat--warn">빠짐: {m}</span>
            ))}
          </div>
          <button type="button" className="exp-card__toggle" onClick={openDetail} aria-expanded={open}>
            {open ? '상세 접기 ▴' : '판독·판단·법령 상세 보기 ▾'}
          </button>
        </div>
      </div>

      {zoom && imgUrl && (
        <div
          className="exp-lightbox"
          role="dialog"
          aria-modal="true"
          aria-label="영수증 원본"
          onClick={() => setZoom(false)}
        >
          <img src={imgUrl} alt={`${item.vendor} 영수증 원본`} onClick={(e) => e.stopPropagation()} />
          <button type="button" className="exp-lightbox__close" onClick={() => setZoom(false)} aria-label="닫기">
            ✕
          </button>
        </div>
      )}

      {open && (
        <div className="exp-card__detail">
          {anaFailed && <p className="cal__err">판독 내용을 불러오지 못했어요.</p>}
          {!analysis && !anaFailed && <p className="ai__hint">읽은 내용을 정리하고 있어요…</p>}
          {analysis && (
            <React.Fragment>
              <Fold
                title="📖 영수증에서 읽은 내용"
                hint={`${analysis.fields.filter((f) => f.read).length}/${analysis.fields.length}개 인식`}
              >
                <ReceiptFields analysis={analysis} />
              </Fold>
              <Fold title="🧭 이렇게 판단했어요" hint={`종합 ${TIER_SHORT_LABELS[analysis.tier] || analysis.tierLabel}`}>
                <ReceiptSteps analysis={analysis} />
              </Fold>
              <Fold title="📚 세법 근거 · 관련 법령" hint={`법령 ${analysis.laws.length}건`}>
                <LawList laws={analysis.laws} note={analysis.lawNote} />
                <h4 className="exp-ana__ttl">AI가 찾은 세법 자료</h4>
                {busy && <p className="ai__hint">관련 세법 자료를 찾고 있어요…</p>}
                {err && <p className="cal__err">{err}</p>}
                {detail && (
                  <React.Fragment>
                    <p style={{ margin: '0 0 8px' }}>{detail.basis}</p>
                    {detail.sources && detail.sources.length > 0 && (
                      <div className="msg-src">
                        <b>확인한 자료 {detail.sources.length}건</b>
                        {detail.sources.map((src, i) => <span key={i}>[{i + 1}] {src}</span>)}
                      </div>
                    )}
                  </React.Fragment>
                )}
              </Fold>
            </React.Fragment>
          )}
          <button type="button" style={{ ...linkBtn, marginTop: 10, color: 'var(--red)' }} onClick={remove}>
            이 영수증 삭제
          </button>
        </div>
      )}
    </li>
  );
}

export function ExpenseTracker({ user, onRequireLogin }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState('');
  const [preview, setPreview] = useState(null); // { url, name } — 업로드 중 보여줄 작은 미리보기
  const [err, setErr] = useState('');
  const fileRef = React.useRef(null);
  const userId = user && user.id;

  const load = () => {
    if (!userId) return;
    setLoading(true);
    api
      .expenses()
      // 방금 올린 영수증이 맨 위에 오도록 최신순으로 보여준다.
      .then((r) => setItems([...((r && r.expenses) || [])].sort((a, b) => b.expenseId - a.expenseId)))
      .catch(() => setErr('지출 목록을 불러오지 못했어요.'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const pickFile = () => fileRef.current && fileRef.current.click();

  const onFile = async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file) return;
    if (!userId) {
      onRequireLogin && onRequireLogin();
      return;
    }
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setErr('JPEG, PNG, WebP 이미지만 올릴 수 있어요.');
      return;
    }
    if (file.size > 4 * 1024 * 1024) {
      setErr('영수증 이미지는 4MB 이하여야 해요.');
      return;
    }
    setErr('');
    const previewUrl = URL.createObjectURL(file);
    setPreview({ url: previewUrl, name: file.name });
    setUploading(true);
    setUploadMsg('영수증을 확인하고 있어요…');
    // 실제 진행 단계를 알 수 없어(Vision 호출 하나로 끝남) 흐름만 보여주는 연출용 타이머다.
    const t1 = setTimeout(() => setUploadMsg('금액·상호·증빙 종류를 읽고 있어요…'), 3000);
    const t2 = setTimeout(() => setUploadMsg('경비 인정 가능성을 판단하고 있어요…'), 7000);
    try {
      await api.uploadReceipt(file);
      load();
    } catch (e2) {
      if (e2 && e2.status === 401) {
        onRequireLogin && onRequireLogin();
      } else {
        setErr('영수증을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.');
      }
    } finally {
      clearTimeout(t1);
      clearTimeout(t2);
      setUploading(false);
      setUploadMsg('');
      URL.revokeObjectURL(previewUrl);
      setPreview(null);
    }
  };

  const onDeleted = (id) => setItems((cur) => cur.filter((x) => x.expenseId !== id));
  const onCategoryChanged = (id, category, detail) =>
    setItems((cur) =>
      cur.map((x) =>
        x.expenseId === id
          ? {
              ...x,
              category,
              deductible: detail.deductible,
              tier: detail.tier,
              tierLabel: detail.tierLabel,
              proofValid: detail.proofValid,
              missingFields: detail.missingFields,
            }
          : x
      )
    );

  const total = items.reduce((s, x) => s + x.amount, 0);
  const highCount = items.filter((x) => x.tier === 'high').length;

  return (
    <div className="tool">
      <div className="tool__panel">
        <h2>지출관리 · 영수증 경비 판정</h2>
        <p style={{ margin: '0 0 14px', fontSize: 12.5, color: 'var(--ink-soft)' }}>
          영수증 사진을 올리면 OCR로 내용을 읽고, 사업 경비 인정 가능성과 증빙(세금계산서·카드·현금영수증)
          적격 여부를 알려드려요. 최종 판단은 세무사와 함께 확인해 주세요.
        </p>

        {!userId ? (
          <p className="cvx__empty">
            로그인하면 영수증을 올리고 경비 판정을 받을 수 있어요.{' '}
            {onRequireLogin && (
              <button type="button" style={linkBtn} onClick={onRequireLogin}>로그인</button>
            )}
          </p>
        ) : (
          <React.Fragment>
            <input
              ref={fileRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              capture="environment"
              style={{ display: 'none' }}
              onChange={onFile}
            />
            {uploading ? (
              <div className="exp-analyzing">
                {preview && (
                  <img src={preview.url} alt={`업로드한 영수증: ${preview.name}`} className="exp-analyzing__thumb" />
                )}
                <div className="ai__progress" role="status" aria-live="polite">
                  <span className="typing" aria-hidden="true"><i /><i /><i /></span>
                  <span>{uploadMsg || '영수증을 확인하고 있어요…'}</span>
                </div>
              </div>
            ) : (
              <button type="button" className="exp-upload" onClick={pickFile}>
                📷 영수증 올리기
              </button>
            )}
            {err && <p className="cal__err">{err}</p>}

            {loading ? (
              <p className="ai__hint">불러오는 중…</p>
            ) : items.length === 0 ? (
              <p className="cvx__empty" style={{ marginTop: 14 }}>아직 올린 영수증이 없어요.</p>
            ) : (
              <React.Fragment>
                <ul className="exp-list exp-list--cards">
                  {items.map((it) => (
                    <ReceiptCard
                      key={it.expenseId}
                      item={it}
                      onDeleted={onDeleted}
                      onCategoryChanged={onCategoryChanged}
                    />
                  ))}
                </ul>
                <div className="exp-total">
                  <span>합계 · 인정 가능성 높음 {highCount}/{items.length}건</span>
                  <span className="u-num">{total.toLocaleString()}원</span>
                </div>
              </React.Fragment>
            )}
          </React.Fragment>
        )}
      </div>
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
  // 저장된 값이 목록에 없으면(예전 '대전광역시' 형식 등) 첫 항목으로 맞춰 준다
  const pick = (list, v) => (list.indexOf(v) >= 0 ? v : list[0]);
  const [form, setForm] = useState({
    name: user.name,
    email: user.email || '',
    biz: pick(INDUSTRIES, user.biz),
    region: pick(REGIONS, user.region),
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
      // 화면의 user 는 업종을 biz 로 들고 있어 서버 필드명(industry)과 다르다.
      if (onSaved) onSaved({ ...patch, biz: form.biz });
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
            <select style={inputStyle} value={form.biz} onChange={upd('biz')}>
              {INDUSTRIES.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </label>
          <label className="fld"><span>사업장 지역</span>
            <select style={inputStyle} value={form.region} onChange={upd('region')}>
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

export function MyPage({ user, onHome, onLogout, onNavigate, onLoginClick, savedPolicies = [], onToggleSavedPolicy, onOpenRoadmap, onOpenTax, onOpenGov, onProfileSaved }) {
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

  // 창업 로드맵 카드: 체크 진행률 대신 단계 목록과 목표 수를 보여준다.
  const rmTotal = ROADMAP.reduce((n, s) => n + (ROADMAP_TASKS[s.k] || []).length, 0);

  return (
    <div className="mp">
      <aside className="mp-side">
        <button className="mp-brand" type="button" onClick={onHome}>
          <span className="brand__mark" aria-hidden="true">ON</span>
          창업ON
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
                <h2 className="mp-card__title">창업 로드맵</h2>
                <span className="mp-card__link">로드맵 보기 ›</span>
              </div>
              <p className="mp-recap">{ROADMAP.length}단계 · 근거 등급이 붙은 목표 {rmTotal}개</p>
              <ol className="mp-rmsteps">
                {ROADMAP.map((s, i) => (
                  <li key={s.k}><span className="mp-rmsteps__no">{i + 1}</span>{s.t}</li>
                ))}
              </ol>
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
        ) : menu === 'saved' ? (
          <SavedGov user={user} savedPolicies={savedPolicies} onToggleSave={onToggleSavedPolicy} />
        ) : menu === 'settings' ? (
          <ProfileSettings user={user} only="notif" />
        ) : menu === 'expenses' ? (
          <ExpenseTracker user={user} onRequireLogin={onLoginClick} />
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
