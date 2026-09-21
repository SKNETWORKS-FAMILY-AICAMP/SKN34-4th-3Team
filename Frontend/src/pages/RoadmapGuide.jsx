import React, { useState } from 'react';
import { useApi } from '../api.js';
import {
  ROADMAP, ROADMAP_GOALS, ROADMAP_TASKS, RM_GRADES, RM_AS_OF,
  RG_CHAT_RULES, RG_CHAT_CHIPS, DEFAULT_BIZ, DEFAULT_REGION,
} from '../constants.js';
import { AiConsult } from '../components/AiConsult.jsx';
import { rmIcon } from '../components/roadmapIcons.jsx';

function GradeBadge({ grade }) {
  const g = RM_GRADES[grade];
  return (
    <span className={'rg2__badge rg2__badge--' + (g ? g.cls : 'ref')} title={g ? g.desc : undefined}>
      {grade}
    </span>
  );
}

export function RoadmapGuide({ user, onRequireLogin }) {
  const [active, setActive] = useState('A');
  const [openTask, setOpenTask] = useState(null); // 근거를 펼친 목표
  // 추천 질문은 서버에서 받아오고, 없으면 화면 기본값을 쓴다
  const { data: roadmapSuggestions } = useApi(
    '/chat/categories/roadmap/suggested-questions',
    RG_CHAT_CHIPS,
    (response) => (response && response.questions && response.questions.length ? response.questions : RG_CHAT_CHIPS),
  );

  const tasks = ROADMAP_TASKS[active] || [];
  const goal = ROADMAP_GOALS[active];

  return (
    <div className="rg2">
      <div className="rz rz--nav is-in">
        <div className="rz__row" role="tablist" aria-label="창업 단계">
          {ROADMAP.map((s, i) => (
            <React.Fragment key={s.k}>
              {i > 0 && <div className="rz__sep" aria-hidden="true">›</div>}
              <button
                type="button"
                role="tab"
                aria-selected={s.k === active}
                className={'rz__step' + (s.k === active ? ' is-active' : '')}
                onClick={() => { setActive(s.k); setOpenTask(null); }}
              >
                <span className="rz__ico">{rmIcon(s.k)}</span>
                <span className="rz__phase">{s.phase}</span>
                <span className="rz__t">{s.t}</span>
              </button>
            </React.Fragment>
          ))}
        </div>
      </div>

      <div className="rg2__cols">
        <section className="rg2__list">
          {goal && (
            <div className="rg2__goal">
              <span className="rg2__goallabel">이 단계 목표</span>
              <b className="rg2__goaltext">{goal.goal}</b>
              {goal.span && <span className="rg2__goalspan">{goal.span}</span>}
            </div>
          )}

          <details className="rg2__legend">
            <summary>근거 등급이 뭔가요?</summary>
            <ul>
              {Object.entries(RM_GRADES).map(([name, g]) => (
                <li key={name}>
                  <span className={'rg2__badge rg2__badge--' + g.cls}>{name}</span>
                  <span>{g.desc}</span>
                </li>
              ))}
            </ul>
          </details>

          <ul className="rg2__tasks">
            {tasks.map((t, i) => {
              const open = openTask === i;
              const grade = RM_GRADES[t.grade];
              return (
                <li key={i} className={'rg2__task' + (open ? ' is-open' : '')}>
                  <button
                    type="button"
                    className="rg2__taskbtn"
                    aria-expanded={open}
                    onClick={() => setOpenTask(open ? null : i)}
                  >
                    <span className="rg2__no" aria-hidden="true">{i + 1}</span>
                    <span className="rg2__tasktitle">
                      {t.t}
                      {t.key && <em className="rg2__key">놓치면 손해</em>}
                    </span>
                    <GradeBadge grade={t.grade} />
                    <i className="rg2__taskcaret" aria-hidden="true">{open ? '−' : '+'}</i>
                  </button>
                  {open && (
                    <div className="rg2__taskinfo">
                      {t.grade === '미확인' && (
                        <p className="rg2__warn">
                          근거를 확인하지 못한 항목이에요. 공고 원문 등 공식 자료로 반드시 다시 확인하세요.
                        </p>
                      )}
                      <p className="rg2__tasklabel">근거</p>
                      <p className="rg2__taskwhy">{t.basis}</p>
                      {t.asOf && <p className="rg2__asof">기준: {t.asOf} · 개정될 수 있어요</p>}
                      {t.src && t.src.length > 0 && (
                        <React.Fragment>
                          <p className="rg2__tasklabel">출처</p>
                          <ul className="rg2__src">
                            {t.src.map((s) => (
                              <li key={s.url}>
                                <a href={s.url} target="_blank" rel="noreferrer">{s.label} ↗</a>
                              </li>
                            ))}
                          </ul>
                        </React.Fragment>
                      )}
                      {grade && <p className="rg2__gradenote">{t.grade} · {grade.desc}</p>}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>

          <p className="rg2__disc">
            {RM_AS_OF} 기준으로 조사한 내용이에요. 금액·비율·요건은 개정될 수 있으니 실제 신청 전에 원문을
            확인하고, 세금 관련 판단은 세무사와 함께 확인해 주세요.
          </p>
        </section>

        <aside className="rg2__chat">
          <AiConsult
            user={user || { biz: DEFAULT_BIZ, region: DEFAULT_REGION }}
            rules={RG_CHAT_RULES}
            suggestions={roadmapSuggestions}
            title="로드맵 AI 코치"
            category="roadmap"
            roadmapStep={active}
            allowSampleFallback={false}
            onRequireLogin={onRequireLogin}
            compact
          />
        </aside>
      </div>
    </div>
  );
}

/* ===== AI 세무 Assistant (예시 대화 + 실시간) ===== */
