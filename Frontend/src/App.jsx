import React, { useState, useEffect, useRef, useCallback } from 'react';
import { api, getToken } from './api.js';
import { loadRoadmapDone, clearLegacyRoadmapDone } from './utils.js';
import { USER_STORE_KEY } from './constants.js';
import { ScrollProgress, FloatingThemeToggle } from './components/common.jsx';
import { PageTour } from './components/PageTour.jsx';
import { Nav } from './components/Nav.jsx';
import { LoginModal } from './components/LoginModal.jsx';
import { SubPage } from './pages/SubPage.jsx';
import { MyPage } from './pages/MyPage.jsx';
import { Home } from './pages/Home.jsx';
import { MobileApp } from './mobile/MobileApp.jsx';
import { useIsMobile } from './mobile/useIsMobile.js';
import { WebTabBar } from './web/WebTabBar.jsx';
import { WebToday } from './web/WebToday.jsx';

// 반응형 웹앱(/web.html)은 주소 해시에 현재 화면을 남긴다(#/roadmap · #/mypage).
const WEB_PAGES = ['roadmap', 'tax', 'expenses', 'gov', 'bizplan'];
function viewFromHash() {
  const key = window.location.hash.replace(/^#\/?/, '');
  if (key === 'mypage') return { view: 'mypage', pageKey: 'tax' };
  if (WEB_PAGES.includes(key)) return { view: 'page', pageKey: key };
  return { view: 'home', pageKey: 'tax' };
}

// variant='web': 반응형 웹앱(/web.html). 기존 PC 화면을 모든 폭에서 쓰고, 폭에 맞춰 배치만 바꾼다(web/web.css).
// 그 외(index.html)에는 폭 768px 이하에서 모바일 앱, 넓으면 기존 PC 화면.
export function App({ variant } = {}) {
  const isWeb = variant === 'web';
  const [user, setUser] = useState(null);
  const [view, setView] = useState(() => (isWeb ? viewFromHash().view : 'home'));
  const [pageKey, setPageKey] = useState(() => (isWeb ? viewFromHash().pageKey : 'tax'));
  const [loginOpen, setLoginOpen] = useState(false);
  const [afterLogin, setAfterLogin] = useState(null);
  const bizplanUnsavedRef = useRef(false);
  const reportBizplanUnsaved = useCallback((unsaved) => { bizplanUnsavedRef.current = unsaved; }, []);
  // 창업 로드맵 체크 상태 — 로드맵 페이지와 마이페이지가 공유. 서버(user_roadmap_progress)가 원본(아래 [userId] effect).
  const [roadmapDone, setRoadmapDone] = useState({});
  // 관심 정책 — 서버(saved_policies)가 원본. 화면 이동으로 MyPage가 언마운트돼도 유지되게 여기서 든다.
  const [savedPolicies, setSavedPolicies] = useState([]);
  // 화면 폭 768px 이하에서는 모바일 전용 웹앱(src/mobile)을 보여준다. 데이터·API는 PC와 같이 쓴다.
  const isMobile = useIsMobile();

  // 웹앱: 화면이 바뀌면 주소에 남기고, 뒤로 가기 · 앞으로 가기로 화면을 되돌린다.
  useEffect(() => {
    if (!isWeb) return undefined;
    const onPop = () => {
      const next = viewFromHash();
      setView(next.view);
      setPageKey(next.pageKey);
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, [isWeb]);
  useEffect(() => {
    if (!isWeb) return;
    const hash = view === 'page' ? `#/${pageKey}` : view === 'mypage' ? '#/mypage' : '';
    if ((window.location.hash || '') !== hash) window.history.pushState(null, '', hash || window.location.pathname);
  }, [isWeb, view, pageKey]);

  // 이전 버전의 사용자 캐시는 더 이상 읽지 않는다.
  useEffect(() => {
    try { localStorage.removeItem(USER_STORE_KEY); } catch { /* 저장소 접근 불가 */ }
  }, []);

  // 토큰으로 사용자 복원을 마쳤는지(웹앱 홈이 복원 전에 로그인 안내를 잠깐 띄우지 않게).
  const [authReady, setAuthReady] = useState(() => !getToken());
  // 토큰으로 사용자와 사업자 정보를 DB에서 복원한다.
  useEffect(() => {
    let alive = true;
    const token = getToken();
    api
      .currentUser()
      .then((u) => {
        if (alive && token === getToken()) setUser(u);
      })
      .catch(() => {
        /* Backend 미실행·타임아웃 — 저장된 사용자 정보로 대체하지 않는다 */
      })
      .finally(() => { if (alive) setAuthReady(true); });
    return () => { alive = false; };
  }, []);

  const userId = user && user.id;

  // 계정이 바뀌면 그 계정의 진행률을 서버에서 받는다. 로그아웃이면 비운다(비로그인 체크는 버림).
  useEffect(() => {
    setRoadmapDone({});
    if (!userId) return undefined;
    let alive = true;
    api
      .roadmapProgress()
      .then((r) => {
        if (!alive) return;
        const done = Object.fromEntries((r.done || []).map((key) => [key, true]));
        const legacy = loadRoadmapDone(userId);
        const legacyKeys = Object.keys(legacy).filter((key) => legacy[key] && /^[A-Z]:\d+$/.test(key));
        // 서버가 비어 있고 이 브라우저에 예전 체크가 있으면 한 번 옮기고, 다 올라가면 지운다.
        if (!Object.keys(done).length && legacyKeys.length) {
          setRoadmapDone(Object.fromEntries(legacyKeys.map((key) => [key, true])));
          Promise.all(legacyKeys.map((key) => api.setRoadmapTask(key, true)))
            .then(() => clearLegacyRoadmapDone(userId))
            .catch(() => { /* 다음 로그인 때 다시 시도 */ });
          return;
        }
        setRoadmapDone(done);
      })
      .catch(() => { /* Backend 미실행·토큰 만료 — 빈 진행률 유지 */ });
    return () => { alive = false; };
  }, [userId]);

  // 화면을 먼저 바꾸고 달라진 항목만 서버에 보낸다. 실패한 항목은 이전 값으로 되돌린다.
  // 비로그인 체크는 화면에만 둔다.
  const updateRoadmapDone = (fn) => {
    const prev = roadmapDone;
    const next = typeof fn === 'function' ? fn(prev) : fn;
    setRoadmapDone(next);
    if (!userId) return;
    const changed = [...new Set([...Object.keys(prev), ...Object.keys(next)])]
      .filter((key) => !!prev[key] !== !!next[key]);
    changed.forEach((key) => {
      api.setRoadmapTask(key, !!next[key]).catch(() => {
        setRoadmapDone((cur) => ({ ...cur, [key]: !!prev[key] }));
      });
    });
  };

  useEffect(() => {
    if (!userId) {
      setSavedPolicies([]);
      return undefined;
    }
    let alive = true;
    api
      .savedPolicies()
      .then((r) => alive && setSavedPolicies(r.policies || []))
      .catch(() => { /* Backend 미실행·토큰 만료 — 빈 목록 유지 */ });
    return () => { alive = false; };
  }, [userId]);

  // 서버 반영이 성공한 뒤에만 화면 목록을 바꾼다. 실패는 호출부가 메시지로 알린다.
  const toggleSavedPolicy = async (item) => {
    const id = item.policyId;
    if (savedPolicies.some((p) => p.policyId === id)) {
      await api.unsavePolicy(id);
      setSavedPolicies((cur) => cur.filter((p) => p.policyId !== id));
    } else {
      await api.savePolicy(id);
      // 홈 공고 항목은 PolicyItem 모양이 아니다. 화면 표시가 같도록 서버 목록으로 교체한다.
      const r = await api.savedPolicies();
      setSavedPolicies(r.policies || []);
    }
  };

  const goMyPage = () => {
    if (user) setView('mypage');
    else {
      setAfterLogin('mypage');
      setLoginOpen(true);
    }
  };

  const confirmLeaveBizplan = () => {
    if (view !== 'page' || pageKey !== 'bizplan' || !bizplanUnsavedRef.current) return true;
    if (!window.confirm('저장하지 않은 사업계획서 내용이 있습니다. 저장하지 않고 벗어나면 변경 내용이 삭제됩니다. 계속할까요?')) return false;
    bizplanUnsavedRef.current = false;
    return true;
  };

  const handleNavigate = (key) => {
    if (key !== 'bizplan' && !confirmLeaveBizplan()) return;
    if (key === 'home') {
      setView('home');
      window.scrollTo(0, 0);
      return;
    }
    if (key === 'mypage') {
      goMyPage();
      return;
    }
    setPageKey(key); // 'roadmap' | 'tax' | 'expenses' | 'gov'
    setView('page');
    window.scrollTo(0, 0);
  };

  const handleLoginClick = () => {
    if (user) {
      if (!confirmLeaveBizplan()) return;
      api.logout();
      setUser(null);
      setView('home');
    } else {
      setAfterLogin(null);
      setLoginOpen(true);
    }
  };

  const handleLoginSuccess = (u) => {
    setUser(u);
    setLoginOpen(false);
    if (afterLogin === 'mypage') setView('mypage');
    setAfterLogin(null);
  };

  const requireMyPageLogin = useCallback(() => {
    setAfterLogin('mypage');
    setLoginOpen(true);
  }, []);

  const modal = loginOpen && (
    <LoginModal onClose={() => setLoginOpen(false)} onSuccess={handleLoginSuccess} />
  );
  // 웹앱 휴대폰 폭의 하단 탭바(넓은 화면에서는 web.css가 숨긴다)
  const tabbar = isWeb && (
    <WebTabBar
      current={view === 'page' ? pageKey : view === 'mypage' && user ? 'mypage' : 'home'}
      onNavigate={handleNavigate}
    />
  );

  if (isMobile && !isWeb) {
    return (
      <React.Fragment>
        <MobileApp
          user={user}
          roadmapDone={roadmapDone}
          setRoadmapDone={updateRoadmapDone}
          savedPolicies={savedPolicies}
          onToggleSavedPolicy={toggleSavedPolicy}
          onLogin={() => { setAfterLogin(null); setLoginOpen(true); }}
          onLogout={() => { api.logout(); setUser(null); }}
          onProfileSaved={setUser}
        />
        {modal}
      </React.Fragment>
    );
  }

  if (view === 'mypage' && user) {
    return (
      <React.Fragment>
        <MyPage
          user={user}
          onProfileSaved={setUser}
          onHome={() => setView('home')}
          onLogout={() => {
            api.logout();
            setUser(null);
            setView('home');
          }}
          onNavigate={handleNavigate}
          onLoginClick={handleLoginClick}
          onRequireLogin={requireMyPageLogin}
          roadmapDone={roadmapDone}
          savedPolicies={savedPolicies}
          onToggleSavedPolicy={toggleSavedPolicy}
          onOpenRoadmap={() => handleNavigate('roadmap')}
          onOpenTax={() => handleNavigate('tax')}
          onOpenGov={() => handleNavigate('gov')}
        />
        <FloatingThemeToggle />
        <PageTour page="mypage" userId={user.id} />
        {tabbar}
        {modal}
      </React.Fragment>
    );
  }

  if (view === 'page') {
    return (
      <React.Fragment>
        <ScrollProgress />
        <SubPage
          pageKey={pageKey}
          user={user}
          onHome={() => handleNavigate('home')}
          onLoginClick={handleLoginClick}
          onNavigate={handleNavigate}
          onBizplanUnsavedChange={reportBizplanUnsaved}
          roadmapDone={roadmapDone}
          setRoadmapDone={updateRoadmapDone}
          savedPolicies={savedPolicies}
          onToggleSavedPolicy={toggleSavedPolicy}
        />
        <FloatingThemeToggle />
        {/* 사업계획서는 단계별 안내와 '사용 가이드' 버튼을 페이지 안에 따로 둔다. */}
        {pageKey !== 'bizplan' && <PageTour key={pageKey} page={pageKey} userId={user && user.id} />}
        {tabbar}
        {modal}
      </React.Fragment>
    );
  }

  return (
    <React.Fragment>
      <ScrollProgress />
      {/* 머리글은 홈 본문 축소(.home-scale)의 영향을 받지 않게 밖에 두어 다른 페이지와 크기를 맞춘다. */}
      <Nav user={user} onLoginClick={handleLoginClick} onNavigate={handleNavigate} />
      {/* 웹앱 태블릿 · PC: 홈 맨 위에 오늘 챙길 일(로그인 전에는 로그인 안내). 휴대폰 폭에서는 그리지 않는다. */}
      {isWeb && !isMobile && (user || authReady) && (
        <WebToday user={user} roadmapDone={roadmapDone} savedPolicies={savedPolicies}
          onNavigate={handleNavigate} onLogin={handleLoginClick} />
      )}
      <div className="home-scale">
        <Home
          onNavigate={handleNavigate}
          user={user}
          savedPolicies={savedPolicies}
          onToggleSavedPolicy={toggleSavedPolicy}
          onLoginClick={handleLoginClick}
        />
        <footer className="foot">
          <div className="wrap">창업ON · 공공데이터 기반 창업 지원 공고 큐레이션</div>
        </footer>
      </div>
      <FloatingThemeToggle />
      {tabbar}
      {modal}
    </React.Fragment>
  );
}

export default App;
