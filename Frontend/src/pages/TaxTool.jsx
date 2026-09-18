import React, { useState, useEffect } from 'react';
// 참고: 2026-09-14 기준 어디서도 렌더링하지 않는 화면입니다(메뉴에서 빠짐). 삭제하지 않고 보존만 합니다.
import { TAX_SCHEDULE } from '../constants.js';
import { api } from '../api.js';

export function TaxTool() {
  const [area, setArea] = useState('outside'); // outside | metro | declining
  const [youth, setYouth] = useState('yes'); // yes | no
  const [eligible, setEligible] = useState('yes'); // yes | no
  const [srv, setSrv] = useState(null); // Backend Rule Engine 판정 결과

  // Backend: POST /api/tax/tax-reduction/check → 서버 Rule Engine + 근거 조문(DB)
  useEffect(() => {
    let alive = true;
    const ctl = new AbortController();
    api
      .taxCheck(
        {
          region: area === 'metro' ? '서울' : '대전',
          age: youth === 'yes' ? 32 : 45,
          industry: eligible === 'yes' ? '정보통신업' : '부동산업',
        },
        { signal: ctl.signal }
      )
      .then((r) => alive && setSrv(r))
      .catch(() => alive && setSrv(null));
    return () => {
      alive = false;
      ctl.abort();
    };
  }, [area, youth, eligible]);

  let rate = 0;
  let note = '';
  if (eligible === 'no') {
    rate = 0;
    note = '일반음식점·부동산업 등 일부 업종은 창업중소기업 세액감면 대상에서 제외돼요. 업종코드로 대상 여부를 먼저 확인하세요.';
  } else if (area === 'declining') {
    rate = 100;
    note = '인구감소지역에서 창업한 중소기업은 최초 소득 발생 과세연도부터 5년간 100% 감면됩니다.';
  } else if (youth === 'yes' && area === 'outside') {
    rate = 100;
    note = '만 15~34세 청년이 수도권 과밀억제권역 밖에서 창업하면 5년간 소득세·법인세 100% 감면됩니다.';
  } else if (youth === 'yes' && area === 'metro') {
    rate = 50;
    note = '청년 창업이라도 수도권 과밀억제권역 안이면 5년간 50% 감면됩니다.';
  } else if (youth === 'no' && area === 'outside') {
    rate = 50;
    note = '청년 외 창업자가 수도권 과밀억제권역 밖에서 창업하면 5년간 50% 감면됩니다.';
  } else {
    rate = 0;
    note = '청년 외 창업자가 수도권 과밀억제권역 안에서 창업하면 일반적으로 창업 세액감면 대상이 아니에요. (연 수입금액 8,000만 원 이하 등 별도 요건은 추가 확인이 필요합니다.)';
  }

  return (
    <div className="tool">
      <div className="tool__panel">
        <h2>세액감면 판정</h2>
        <div className="field-col">
          <label className="fld">
            <span>창업 지역</span>
            <div className="seg">
              {[
                ['outside', '수도권 과밀억제권역 밖'],
                ['metro', '수도권 과밀억제권역 안'],
                ['declining', '인구감소지역'],
              ].map(([v, l]) => (
                <button key={v} type="button" aria-pressed={area === v} onClick={() => setArea(v)}>{l}</button>
              ))}
            </div>
          </label>
          <label className="fld">
            <span>대표자 연령</span>
            <div className="seg">
              <button type="button" aria-pressed={youth === 'yes'} onClick={() => setYouth('yes')}>청년 (만 15~34세)</button>
              <button type="button" aria-pressed={youth === 'no'} onClick={() => setYouth('no')}>그 외</button>
            </div>
          </label>
          <label className="fld">
            <span>감면 대상 업종</span>
            <div className="seg">
              <button type="button" aria-pressed={eligible === 'yes'} onClick={() => setEligible('yes')}>해당 (제조·정보통신 등)</button>
              <button type="button" aria-pressed={eligible === 'no'} onClick={() => setEligible('no')}>제외 업종</button>
            </div>
          </label>
        </div>

        <div className="result">
          <p className="result__label">예상 세액감면율</p>
          <div className="result__rate u-num">
            {rate}%{rate > 0 && <small>· 5년간</small>}
          </div>
          <p className="result__note">
            {note}
            {rate > 0 && ' 감면 기간은 최초 소득이 발생한 과세연도와 그 다음 4개 과세연도입니다.'}
          </p>
          <p className="result__cite">
            근거 · 조세특례제한법 제6조(창업중소기업 등에 대한 세액감면) · 실제 적용은 세무대리인 확인이 필요합니다.
          </p>

          {/* Backend TaxReductionResponse: legalBasis는 문자열, reasons는 문자열 배열.
              서버 판정은 로그인 사용자의 온보딩 프로필(나이·창업일·업종) 기준이라
              위 라디오 선택과 다를 수 있다. */}
          {srv && srv.legalBasis && (
            <div className="msg-src" style={{ maxWidth: 'none', marginTop: 12 }}>
              <b>
                서버 판정 · {srv.eligible ? '감면 대상' : '감면 대상 아님'}
                {srv.llmUsed ? ' (AI 근거 설명)' : ''}
              </b>
              <p style={{ margin: '6px 0 0', fontSize: 12.5, lineHeight: 1.6 }}>{srv.legalBasis}</p>
              {Array.isArray(srv.reasons) && srv.reasons.length > 0 && (
                <ul style={{ margin: '8px 0 0 16px', padding: 0, fontSize: 12, lineHeight: 1.6 }}>
                  {srv.reasons.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              )}
              <p style={{ margin: '8px 0 0', fontSize: 11.5, color: 'var(--ink-faint)' }}>
                내 프로필 기준 판정입니다. 위 선택값과 다를 수 있습니다.
              </p>
            </div>
          )}
        </div>
      </div>

      <div className="tool__panel">
        <h2>주요 신고 일정</h2>
        <ul className="cal-list">
          {TAX_SCHEDULE.map((s) => (
            <li key={s.when}>
              <span>{s.what}</span>
              <b className="u-num">{s.when}</b>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/* ===== 창업 로드맵 가이드 (AI 도움말 포함) ===== */
/* 단계별로 연결되는 지원사업 (GOV_LISTINGS id) */
