import { useEffect, useState } from 'react';

// 화면 폭이 768px 이하이면 true. 창 크기를 바꾸거나 기기를 돌리면 바로 다시 판단한다.
const QUERY = '(max-width: 768px)';

export function useIsMobile() {
  const get = () => typeof window !== 'undefined' && !!window.matchMedia && window.matchMedia(QUERY).matches;
  const [mobile, setMobile] = useState(get);
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const mq = window.matchMedia(QUERY);
    const onChange = () => setMobile(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return mobile;
}
