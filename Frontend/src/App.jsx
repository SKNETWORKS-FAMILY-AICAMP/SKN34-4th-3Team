import React, { useState, useEffect } from 'react';
import { api } from './api.js';
import { loadStoredUser, loadRoadmapDone, saveRoadmapDone, ROADMAP_KEY } from './utils.js';
import { DEFAULT_BIZ, DEFAULT_REGION, USER_STORE_KEY } from './constants.js';
import { ScrollProgress, FloatingThemeToggle } from './components/common.jsx';
import { Nav } from './components/Nav.jsx';
import { LoginModal } from './components/LoginModal.jsx';
import { SubPage } from './pages/SubPage.jsx';
import { MyPage } from './pages/MyPage.jsx';
import { Home } from './pages/Home.jsx';

export function App() {
  // 로그인 유지: 로그아웃 전까지 새로고침해도 세션 유지 (localStorage)
  const [user, setUser] = useState(loadStoredUser);
  const [view, setView] = useState('home');
  const [pageKey, setPageKey] = useState('tax');
  const [loginOpen, setLoginOpen] = useState(false);
  const [afterLogin, setAfterLogin] = useState(null);
  // 창업 로드맵 진행 상태 — 로드맵 페이지와 마이페이지가 공유. 계정별로 localStorage 에 남긴다(아래 [userId] effect).
  const [roadmapDone, setRoadmapDone] = useState({});
  // 관심 정책 — 서버(saved_policies)가 원본. 화면 이동으로 MyPage가 언마운트돼도 유지되게 여기서 든다.
  const [savedPolicies, setSavedPolicies] = useState([]);

  useEffect(() => {
    try {
      if (user) localStorage.setItem(USER_STORE_KEY, JSON.stringify(user));
      else localStorage.removeItem(USER_STORE_KEY);
    } catch (e) {
      /* 저장 불가 환경은 무시 */
    }
  }, [user]);

  // localStorage 의 user 는 화면 유지용일 뿐 토큰이 살아 있다는 보장이 아니다.
  // Backend 에 물어 실제 세션을 확인한다. 토큰이 없거나 만료면 me() 가 null 을 준다.
  useEffect(() => {
    let alive = true;
    api
      .me()
      .then((u) => {
        if (!alive) return;
        if (u) {
          setUser((cur) => ({
            ...(cur || { biz: DEFAULT_BIZ, region: DEFAULT_REGION }),
            id: u.id,
            name: u.name || (cur && cur.name) || '회원',
            email: u.email,
            region: u.region || (cur && cur.region),
          }));
        } else {
          // 저장된 화면 상태만 남고 토큰이 죽은 경우 — 로그아웃 상태로 맞춘다.
          setUser(null);
        }
      })
      .catch(() => {
        /* Backend 미실행·타임아웃 — 토큰은 그대로 두고 화면 상태를 유지한다 */
      });
    return () => { alive = false; };
  }, []);

  const userId = user && user.id;

  // 계정이 바뀌면 그 계정의 진행률로 교체한다. 로그아웃이면 비운다(비로그인 체크는 버림).
  useEffect(() => {
    setRoadmapDone(userId ? loadRoadmapDone(userId) : {});
  }, [userId]);

  // 저장 effect 대신 setter 에서 저장한다 — 계정 전환 직후 이전 상태가 새 계정 키에 덮어써지지 않게.
  const updateRoadmapDone = (fn) =>
    setRoadmapDone((d) => {
      const next = typeof fn === 'function' ? fn(d) : fn;
      if (userId) saveRoadmapDone(userId, next);
      return next;
    });

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

  const handleNavigate = (key) => {
    if (key === 'home') {
      setView('home');
      window.scrollTo(0, 0);
      return;
    }
    if (key === 'mypage') {
      goMyPage();
      return;
    }
    setPageKey(key); // 'roadmap' | 'tax' | 'gov'
    setView('page');
    window.scrollTo(0, 0);
  };

  const handleLoginClick = () => {
    if (user) {
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

  const modal = loginOpen && (
    <LoginModal onClose={() => setLoginOpen(false)} onSuccess={handleLoginSuccess} />
  );

  if (view === 'mypage' && user) {
    return (
      <React.Fragment>
        <MyPage
          user={user}
          onProfileSaved={(patch) => setUser((cur) => ({ ...cur, ...patch }))}
          onHome={() => setView('home')}
          onLogout={() => {
            api.logout();
            setUser(null);
            setView('home');
          }}
          onNavigate={handleNavigate}
          onLoginClick={handleLoginClick}
          roadmapDone={roadmapDone}
          savedPolicies={savedPolicies}
          onToggleSavedPolicy={toggleSavedPolicy}
          onOpenRoadmap={() => handleNavigate('roadmap')}
          onOpenTax={() => handleNavigate('tax')}
          onOpenGov={() => handleNavigate('gov')}
        />
        <FloatingThemeToggle />
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
          onHome={() => setView('home')}
          onLoginClick={handleLoginClick}
          onNavigate={handleNavigate}
          roadmapDone={roadmapDone}
          setRoadmapDone={updateRoadmapDone}
          savedPolicies={savedPolicies}
          onToggleSavedPolicy={toggleSavedPolicy}
        />
        <FloatingThemeToggle />
        {modal}
      </React.Fragment>
    );
  }

  return (
    <React.Fragment>
      <ScrollProgress />
      <div className="home-scale">
        <Nav user={user} onLoginClick={handleLoginClick} onNavigate={handleNavigate} />
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
      {modal}
    </React.Fragment>
  );
}

export default App;
