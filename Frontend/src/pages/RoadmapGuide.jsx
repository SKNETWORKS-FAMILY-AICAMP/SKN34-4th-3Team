import React, { useState } from 'react';
import { useApi } from '../api.js';
import { ROADMAP, ROADMAP_GOALS, ROADMAP_TASKS, RG_CHAT_RULES, RG_CHAT_CHIPS, DEFAULT_BIZ, DEFAULT_REGION } from '../constants.js';
import { AiConsult } from '../components/AiConsult.jsx';
import { rmIcon, rmDoneIcon } from '../components/roadmapIcons.jsx';

export function RoadmapGuide({ user, done = {}, setDone, onRequireLogin }) {
  const [active, setActive] = useState('A');
  const [openTask, setOpenTask] = useState(null); // 설명을 펼친 체크리스트 항목
  // 추천 질문은 서버에서 받아오고, 없으면 화면 기본값을 쓴다
  const { data: roadmapSuggestions } = useApi(
    '/chat/categories/roadmap/suggested-questions',
    RG_CHAT_CHIPS,
    (response) => (response && response.questions && response.questions.length ? response.questions : RG_CHAT_CHIPS),
  );

  const step = ROADMAP.find((s) => s.k === active);
  const tasks = ROADMAP_TASKS[active] || [];
  const goal = ROADMAP_GOALS[active];
  const totalTasks = ROADMAP.reduce((n, s) => n + (ROADMAP_TASKS[s.k] || []).length, 0);
  const totalDone = Object.values(done).filter(Boolean).length;
  const overallPct = totalTasks ? Math.round((totalDone / totalTasks) * 100) : 0;

  const toggle = (i) =>
    setDone((d) => ({ ...d, [`${active}:${i}`]: !d[`${active}:${i}`] }));
  const stepDone = (k) => {
    const t = ROADMAP_TASKS[k] || [];
    return t.length > 0 && t.every((_, i) => done[`${k}:${i}`]);
  };

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
                className={
                  'rz__step' +
                  (s.k === active ? ' is-active' : '') +
                  (stepDone(s.k) ? ' is-done' : '')
                }
                onClick={() => { setActive(s.k); setOpenTask(null); }}
              >
                <span className="rz__ico">{stepDone(s.k) ? rmDoneIcon() : rmIcon(s.k)}</span>
                <span className="rz__phase">{s.phase}</span>
                <span className="rz__t">{s.t}</span>
              </button>
            </React.Fragment>
          ))}
        </div>
      </div>

      <p className="rg2__prog">
        전체 진행률 <b className="u-num">{overallPct}%</b> · {totalDone} / {totalTasks} 작업 완료
      </p>

      <div className="rg2__cols">
        <section className="rg2__list">
          {goal && (
            <div className="rg2__goal">
              <span className="rg2__goallabel">이 단계 목표</span>
              <b className="rg2__goaltext">{goal.goal}</b>
              <span className="rg2__goalspan">{goal.span}</span>
            </div>
          )}
          <ul className="rg2__tasks">
            {tasks.map((t, i) => {
              const d = !!done[`${active}:${i}`];
              const open = openTask === i;
              return (
                <li key={i} className={'rg2__task' + (d ? ' is-done' : '')}>
                  <div className="rg2__taskrow">
                    {/* 체크는 네모를 눌렀을 때만, 제목을 누르면 설명이 열린다 */}
                    <input
                      type="checkbox"
                      checked={d}
                      onChange={() => toggle(i)}
                      aria-label={`${t.t} 완료 표시`}
                    />
                    <button
                      type="button"
                      className="rg2__taskbtn"
                      aria-expanded={open}
                      onClick={() => setOpenTask(open ? null : i)}
                    >
                      <span>{t.t}</span>
                      <i className="rg2__taskcaret" aria-hidden="true">{open ? '−' : '+'}</i>
                    </button>
                  </div>
                  {open && (
                    <div className="rg2__taskinfo">
                      <p className="rg2__tasklabel">왜 필요한가요?</p>
                      <p className="rg2__taskwhy">{t.why}</p>
                      {t.mk && (
                        <p className="rg2__taskmeta">
                          <span>{t.mk}</span>
                          <b>{t.mv}</b>
                        </p>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
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
