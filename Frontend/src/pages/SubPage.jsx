import React, { useState } from 'react';
import { LogoMark, BrandWord } from '../components/LogoMark.jsx';
import { MenuDrawer } from '../components/MenuDrawer.jsx';
import { Nav } from '../components/Nav.jsx';
import { RoadmapGuide } from './RoadmapGuide.jsx';
import { TaxAssistantPage } from './TaxAssistantPage.jsx';
import { ExpenseTracker } from './ExpenseTracker.jsx';
import { BusinessPlanPage } from './BusinessPlanPage.jsx';
import { AnnouncementAnalyzer } from './AnnouncementAnalyzer.jsx';

export function SubPage({ pageKey, user, onHome, onLoginClick, onNavigate, roadmapDone, setRoadmapDone, savedPolicies = [], onToggleSavedPolicy }) {
  const meta =
    {
      roadmap: { title: '창업 로드맵' },
      tax: { title: 'AI 세무 Assistant' },
      expenses: { title: '지출관리' },
      bizplan: { title: '사업계획서' },
      gov: { title: '공고지원 AI' },
    }[pageKey] || { title: '창업ON' };

  const slim = pageKey === 'roadmap' || pageKey === 'tax' || pageKey === 'gov' || pageKey === 'expenses' || pageKey === 'bizplan';
  const [menuOpen, setMenuOpen] = useState(false);

  const body = (
    <React.Fragment>
      <div className={'fp' + (slim ? ' fp--wide' : '') + (pageKey === 'roadmap' ? ' fp--wideplus' : '')}>
        {/* 사업계획서·지출관리는 페이지 안에 자체 제목이 있어 공용 제목을 겹쳐 두지 않는다. */}
        {pageKey !== 'bizplan' && pageKey !== 'expenses' && (
          <div className={'fp__head' + (slim ? ' fp__head--plain' : '')}>
            <div className="fp__head-in">
              <h1 className="fp__title">{meta.title}</h1>
            </div>
          </div>
        )}
        <div className="fp__body">
          {pageKey === 'roadmap' && (
            <RoadmapGuide
              user={user}
              done={roadmapDone}
              setDone={setRoadmapDone}
              onRequireLogin={onLoginClick}
            />
          )}
          {pageKey === 'gov' && (
            <AnnouncementAnalyzer
              user={user}
              onRequireLogin={onLoginClick}
              savedPolicies={savedPolicies}
              onToggleSavedPolicy={onToggleSavedPolicy}
            />
          )}
          {pageKey === 'tax' && <TaxAssistantPage user={user} onRequireLogin={onLoginClick} />}
          {pageKey === 'expenses' && (
            <div className="exp-page exp-page--full">
              <ExpenseTracker user={user} onRequireLogin={onLoginClick} />
            </div>
          )}
          {pageKey === 'bizplan' && (
            <div className="exp-page exp-page--full">
              <BusinessPlanPage user={user} onRequireLogin={onLoginClick}
                savedPolicies={savedPolicies} onToggleSavedPolicy={onToggleSavedPolicy} />
            </div>
          )}
        </div>
      </div>
      {!slim && (
        <footer className="foot">
          <div className="wrap">창업ON</div>
        </footer>
      )}
    </React.Fragment>
  );

  if (slim) {
    return (
      <React.Fragment>
        <div className="slim-shell">
          <header className="rmhead">
            <div className="rmhead__in">
              <button className="brand" type="button" onClick={onHome}>
                <LogoMark />
                <BrandWord />
              </button>
              <button
                className="hamburger"
                type="button"
                aria-haspopup="dialog"
                aria-expanded={menuOpen}
                aria-label="메뉴 열기"
                onClick={() => setMenuOpen(true)}
              >
                <span /><span /><span />
              </button>
            </div>
          </header>
          {body}
        </div>
        <MenuDrawer
          open={menuOpen}
          onClose={() => setMenuOpen(false)}
          onNavigate={onNavigate}
          user={user}
          onAuth={onLoginClick}
        />
      </React.Fragment>
    );
  }

  return (
    <React.Fragment>
      <Nav user={user} onLoginClick={onLoginClick} onNavigate={onNavigate} />
      {body}
    </React.Fragment>
  );
}

/* ---------- 홈: Hero ---------- */
