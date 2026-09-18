import React, { useState } from 'react';
// 참고: 2026-09-14 기준 어디서도 렌더링하지 않는 화면입니다(메뉴에서 빠짐). 삭제하지 않고 보존만 합니다.
import { useApi } from '../api.js';
import { GOV_LISTINGS, GOV_REGIONS, GOV_TYPES } from '../constants.js';

export function GovExplorer({ saved: savedProp, onToggleSave } = {}) {
  const [region, setRegion] = useState('전체');
  const [types, setTypes] = useState([]);
  const [q, setQ] = useState('');
  const [savedLocal, setSavedLocal] = useState(() => new Set());
  const saved = savedProp || savedLocal;

  const toggleType = (t) =>
    setTypes((p) => (p.includes(t) ? p.filter((x) => x !== t) : [...p, t]));
  const toggleSave =
    onToggleSave ||
    ((id) =>
      setSavedLocal((p) => {
        const n = new Set(p);
        n.has(id) ? n.delete(id) : n.add(id);
        return n;
      }));

  // Backend: GET /api/announcements → 마감 남은 실제 공고 (DB)
  const { data: remote, source: listSrc } = useApi('/announcements?limit=60', null, (raw) =>
    (raw.announcements || []).map((x) => ({
      id: String(x.id),
      title: x.title,
      agency: x.industry || '기타',
      region: x.region || '전국',
      type: x.industry || '기타',
      target: x.target || '',
      amount: x.benefit || '',
      dday: x.dday === null || x.dday === undefined ? 999 : x.dday,
      url: x.sourceUrl,
    }))
  );
  const base = remote && remote.length ? remote : GOV_LISTINGS;
  const live = !!(remote && remote.length);

  const kw = q.trim().toLowerCase();
  const list = base
    .filter((g) => {
      const regionOk =
        region === '전체' ||
        (g.region || '').includes(region) ||
        (g.region || '') === '전국';
      const typeOk = types.length === 0 || types.some((t) => (g.type || '').includes(t));
      const textOk =
        !kw || `${g.title}${g.agency}${g.target}`.toLowerCase().includes(kw);
      return regionOk && typeOk && textOk;
    })
    .sort((a, b) => a.dday - b.dday);

  return (
    <div className="tool">
      <div className="tool__panel">
        <div className="gov__bar">
          <input
            className="gov__search"
            type="text"
            placeholder="공고명 · 기관 검색"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="공고 검색"
          />
          <label className="fld" style={{ minWidth: 120 }}>
            <select value={region} onChange={(e) => setRegion(e.target.value)} aria-label="지역">
              {GOV_REGIONS.map((r) => (
                <option key={r} value={r}>{r === '전체' ? '지역 전체' : r}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="seg" role="group" aria-label="지원 유형">
          {GOV_TYPES.map((t) => (
            <button
              key={t}
              type="button"
              aria-pressed={types.includes(t)}
              onClick={() => toggleType(t)}
            >
              {t}
            </button>
          ))}
          {(types.length > 0 || region !== '전체' || q) && (
            <button type="button" onClick={() => { setTypes([]); setRegion('전체'); setQ(''); }}>
              초기화
            </button>
          )}
        </div>
      </div>

      <p className="gov__count">
        {list.length}건 · 저장 {saved.size}건
        {live ? ' · ● DB 실시간' : ' · ○ 데모 데이터'}
      </p>

      {list.length === 0 ? (
        <div className="gov__empty">조건에 맞는 공고가 없어요. 필터를 줄여보세요.</div>
      ) : (
        <ul className="gov__list">
          {list.map((g) => (
            <li className="gov__card" key={g.id}>
              <h3>{g.title}</h3>
              <span className={'gov__dday' + (g.dday <= 10 ? ' gov__dday--urgent' : '')}>
                {g.dday >= 100 ? '상시' : `D-${g.dday}`}
              </span>
              <p>{g.agency} · {g.amount}</p>
              <div className="gov__tags">
                <span className="gov__tag">{g.region}</span>
                <span className="gov__tag">{g.type}</span>
                <span className="gov__tag">{g.target}</span>
              </div>
              <button
                className="star gov__star"
                type="button"
                aria-pressed={saved.has(g.id)}
                aria-label={`${g.title} 관심 공고 저장`}
                onClick={() => toggleSave(g.id)}
              >
                {saved.has(g.id) ? '★' : '☆'}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ===== 세금상담: 세액감면 판정 ===== */
