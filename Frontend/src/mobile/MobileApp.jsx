// 모바일(768px 이하) 전용 웹앱 틀. 하단 탭 없이 홈 기능 그리드 · 전체 메뉴 · 각 화면 "‹ 홈"으로 이동한다.
// 데이터는 PC와 같은 API·상태(App에서 내려준 로드맵 진행률·저장 공고)를 그대로 쓴다.
import React, { useCallback, useState } from 'react';
import { ToastProvider } from './ui.jsx';
import { MHome } from './MHome.jsx';
import { MMenu } from './MMenu.jsx';
import { MRoadmap } from './MRoadmap.jsx';
import { MTax } from './MTax.jsx';
import { MExpenses } from './MExpenses.jsx';
import { MBizplan } from './MBizplan.jsx';
import { MGov } from './MGov.jsx';
import { MMyPage } from './MMyPage.jsx';

export function MobileApp(props) {
  const { user, onLogin, initialScreen = 'home' } = props;
  const [screen, setScreen] = useState(initialScreen);
  const [params, setParams] = useState({});
  const [menuOpen, setMenuOpen] = useState(false);

  // 이동할 때 함께 넘길 값(예: 홈에서 보낸 질문, 지출관리 필터, 열어 둘 공고)을 params로 전달한다.
  const go = useCallback((key, next = {}) => {
    setMenuOpen(false);
    if (key !== 'home' && !user) {
      onLogin();
      return;
    }
    setParams({ ...next, nonce: Date.now() });
    setScreen(key);
  }, [user, onLogin]);

  const common = {
    ...props,
    params,
    go,
    onHome: () => go('home'),
    onMenu: () => setMenuOpen(true),
  };

  return (
    <ToastProvider>
      <div className="m-app">
        {screen === 'home' && <MHome {...common} />}
        {screen === 'roadmap' && <MRoadmap {...common} />}
        {screen === 'tax' && <MTax {...common} />}
        {screen === 'expenses' && <MExpenses {...common} />}
        {screen === 'bizplan' && <MBizplan {...common} />}
        {screen === 'gov' && <MGov {...common} />}
        {screen === 'mypage' && <MMyPage {...common} />}
        {menuOpen && <MMenu {...common} current={screen} onClose={() => setMenuOpen(false)} />}
      </div>
    </ToastProvider>
  );
}
