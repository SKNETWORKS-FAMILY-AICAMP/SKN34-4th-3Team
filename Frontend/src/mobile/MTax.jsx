// 02 AI 세무 Assistant: 세액감면 자동 판정 카드 → 최근 메시지 4개(위 페이드) → 추천 질문 2개 → 입력창.
// 판정은 기존 /tax/tax-reduction/check(나이·지역·업종), 상담은 기존 채팅 API(category=tax)를 쓴다.
import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api.js';
import { TAX_CHIPS } from '../constants.js';
import { ChatBubbles, ChatInput, FeatureHeader, featureOf, useChat } from './ui.jsx';

export function MTax({ user, params, onHome, onMenu }) {
  const { rows, busy, ready, send } = useChat('tax', user && user.id);
  const [check, setCheck] = useState(null);
  const sentRef = useRef(null);

  useEffect(() => {
    if (!user) return undefined;
    let alive = true;
    api.businessProfile()
      .catch(() => null)
      .then((profile) => api.taxCheck({ region: user.region, age: user.age, industry: profile && profile.industry }))
      .then((r) => alive && setCheck(r))
      .catch(() => alive && setCheck({ error: true }));
    return () => { alive = false; };
  }, [user]);

  // 홈 AI 입력창에서 넘어온 질문은 대화를 불러온 뒤 한 번만 보낸다.
  useEffect(() => {
    if (ready && params.question && sentRef.current !== params.nonce) {
      sentRef.current = params.nonce;
      send(params.question);
    }
  }, [ready, params, send]);

  const reasons = (check && check.reasons) || [];
  const eligible = check && check.eligible;
  const chips = TAX_CHIPS.filter((c) => !c.includes('세액감면')).slice(0, 2);

  return (
    <div className="m-screen">
      <FeatureHeader feature={featureOf('tax')} onHome={onHome} onMenu={onMenu} />
      <div className="m-body">
        <section className={'m-glass m-judge' + (eligible === false ? ' is-no' : '')}>
          <p className="m-judge__kicker">청년창업 세액감면 자동 판정</p>
          <div className="m-judge__row">
            <h2 className="m-judge__title">
              {!check ? '판정 중…' : check.error ? '판정 정보를 불러오지 못했어요'
                : eligible ? '5년간 50% 감면 예상' : '감면 요건을 확인해 주세요'}
            </h2>
            <button type="button" className="m-judge__why" disabled={busy}
              onClick={() => send('청년창업 세액감면 판정 근거를 법령 조문과 함께 알려주세요')}>근거 ›</button>
          </div>
          <p className="m-judge__cond" title={reasons.join(' · ')}>
            {reasons.length ? reasons.map((r) => r.split(' — ')[0]).join(' · ') : '나이 · 창업일 · 업종 기준'}
          </p>
        </section>

        <ChatBubbles rows={rows} max={4} empty="세금 · 경비처리 · 절세 궁금한 점을 물어보세요" />

        <div className="m-sugg">
          {chips.map((c) => (
            <button key={c} type="button" className="m-glass m-sugg__btn" onClick={() => send(c)} disabled={busy}>{c}</button>
          ))}
        </div>
        <ChatInput onSend={send} busy={busy} placeholder="세무 질문을 입력하세요" />
      </div>
    </div>
  );
}
