import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { api } from '../api.js';
import { DEMO_EMAIL, DEMO_PASSWORD, INDUSTRIES, REGIONS, DEFAULT_BIZ, DEFAULT_REGION } from '../constants.js';
import { inputStyle, linkBtn, fieldLabel, socialBtn } from '../utils.js';

export function LoginModal({ onClose, onSuccess }) {
  const [mode, setMode] = useState('login'); // 'login' | 'signup'
  const [name, setName] = useState('');
  const [email, setEmail] = useState(DEMO_EMAIL);
  const [pw, setPw] = useState(DEMO_PASSWORD);
  const [pw2, setPw2] = useState('');
  const [biz, setBiz] = useState(DEFAULT_BIZ);
  const [region, setRegion] = useState(REGIONS[0]); // 처음엔 서울
  const [age, setAge] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // 실제로 Backend에 로그인해 토큰을 받아야 세무·AI 상담 등 인증이 필요한 API가 동작한다.
  // profile이 있으면(회원가입) 서버에 저장하고, 없으면(로그인) 서버에서 읽어와 화면에 쓴다.
  const authenticate = async (doLogin, displayName, profile) => {
    setErr('');
    setBusy(true);
    try {
      const r = await doLogin();
      let biz2 = (profile && profile.biz) || DEFAULT_BIZ;
      let region2 = (profile && profile.region) || DEFAULT_REGION;
      let age2 = profile ? profile.age : null;

      if (profile) {
        // 가입 직후: 입력한 프로필을 서버에 저장 (개인정보 / 사업자 정보 따로)
        try {
          await api.updateMe({ region: profile.region, age: profile.age });
          await api.updateBusinessProfile({ industry: profile.biz });
        } catch (e3) {
          /* 프로필 저장에 실패해도 로그인 자체는 성공 — 마이페이지에서 다시 저장할 수 있다 */
        }
      } else {
        // 로그인: 저장된 프로필을 불러와 반영 (없으면 기본값)
        try {
          const [meRes, bizRes] = await Promise.all([api.me(), api.businessProfile()]);
          if (meRes && meRes.region) region2 = meRes.region;
          if (meRes && meRes.age) age2 = meRes.age;
          if (bizRes && bizRes.industry) biz2 = bizRes.industry;
        } catch (e3) {
          /* 조회 실패 시 기본값으로 진행 */
        }
      }

      onSuccess({
        id: r.userId,
        name: displayName || r.name || name || '정석',
        email: r.email || email,
        biz: biz2,
        region: region2,
        age: age2,
      });
    } catch (e2) {
      setErr(
        e2 && e2.status === 401
          ? '이메일 또는 비밀번호가 올바르지 않습니다.'
          : e2 && e2.status === 409
            ? '이미 가입된 이메일입니다.'
            : 'Backend(:8000)에 연결하지 못했어요. 서버가 떠 있는지 확인해 주세요.'
      );
    } finally {
      setBusy(false);
    }
  };

  const submit = (e) => {
    e.preventDefault();
    if (mode === 'signup') {
      if (pw !== pw2) { setErr('비밀번호가 일치하지 않습니다.'); return; }
      const n = Number(age);
      if (!Number.isFinite(n) || n < 15 || n > 120) { setErr('대표자 연령을 만 나이로 입력해 주세요.'); return; }
      authenticate(() => api.signup(email, pw, name), name, { biz: biz.trim(), region, age: n });
      return;
    }
    authenticate(() => api.login(email, pw));
  };

  // 소셜 로그인은 백엔드에 대응이 없어 데모 계정으로 실제 로그인해 토큰만 받는다.
  const socialDemo = (displayName) => authenticate(() => api.login(DEMO_EMAIL, DEMO_PASSWORD), displayName);

  const isLogin = mode === 'login';

  return (
    <div onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      style={{
        position: 'fixed', inset: 0, zIndex: 90, display: 'grid', placeItems: 'center',
        padding: '20px', background: 'rgba(12,16,30,0.46)', backdropFilter: 'blur(3px)',
      }}>
      <div role="dialog" aria-modal="true" aria-labelledby="login-title"
        style={{
          width: '100%', maxWidth: 380, maxHeight: '90vh', background: 'var(--surface-solid)',
          border: '1px solid var(--line)', borderRadius: 22, boxShadow: 'var(--shadow)',
          // 스크롤은 안쪽에서만 — 바깥 박스가 둥근 모서리를 그대로 유지한다
          overflow: 'hidden', display: 'flex', flexDirection: 'column',
        }}>
        <div className="lgm__scroll" style={{ minHeight: 0, overflowY: 'auto', padding: '26px 24px 24px' }}>
        <button type="button" onClick={onClose} aria-label="닫기"
          style={{
            float: 'right', width: 28, height: 28, margin: '-6px -6px 0 0', border: 0,
            borderRadius: 8, background: 'transparent', color: 'var(--ink-faint)', fontSize: 18, cursor: 'pointer',
          }}>×</button>
        <h2 id="login-title" style={{ margin: '0 0 4px', fontSize: 18, fontWeight: 700, letterSpacing: '-0.02em' }}>
          {isLogin ? '창업ON 로그인' : '창업ON 회원가입'}
        </h2>
        <p style={{ margin: '0 0 18px', fontSize: 12.5, color: 'var(--ink-soft)' }}>
          {isLogin ? '사업자 정보로 맞춤 대시보드를 불러옵니다.' : '3분이면 가입하고 맞춤 추천을 받아요.'}
        </p>

        <form onSubmit={submit}>
          {!isLogin && (
            <label style={{ display: 'block', marginBottom: 12 }}>
              <span style={fieldLabel}>이름</span>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="홍길동" autoComplete="name" style={inputStyle} required />
            </label>
          )}
          <label style={{ display: 'block', marginBottom: 12 }}>
            <span style={fieldLabel}>이메일</span>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" style={inputStyle} required />
          </label>
          <label style={{ display: 'block', marginBottom: 12 }}>
            <span style={fieldLabel}>비밀번호</span>
            <input type="password" value={pw} onChange={(e) => setPw(e.target.value)}
              autoComplete={isLogin ? 'current-password' : 'new-password'} style={inputStyle} required />
          </label>
          {!isLogin && (
            <React.Fragment>
              <label style={{ display: 'block', marginBottom: 12 }}>
                <span style={fieldLabel}>비밀번호 확인</span>
                <input type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} autoComplete="new-password" style={inputStyle} required />
              </label>
              <label style={{ display: 'block', marginBottom: 12 }}>
                <span style={fieldLabel}>업종</span>
                <select value={biz} onChange={(e) => setBiz(e.target.value)} style={inputStyle} required>
                  {INDUSTRIES.map((x) => <option key={x} value={x}>{x}</option>)}
                </select>
              </label>
              <label style={{ display: 'block', marginBottom: 12 }}>
                <span style={fieldLabel}>사업장 지역</span>
                <select value={region} onChange={(e) => setRegion(e.target.value)} style={inputStyle} required>
                  {REGIONS.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </label>
              <label style={{ display: 'block', marginBottom: 12 }}>
                <span style={fieldLabel}>대표자 연령 (만 나이)</span>
                <input type="number" inputMode="numeric" min="15" max="120" value={age}
                  onChange={(e) => setAge(e.target.value)} placeholder="예: 32" style={inputStyle} required />
                <span style={{ display: 'block', marginTop: 5, fontSize: 11.5, color: 'var(--ink-faint)' }}>
                  만 15~34세면 청년창업 세액감면 대상 여부를 함께 판정해 드려요.
                </span>
              </label>
            </React.Fragment>
          )}
          {err && <p style={{ margin: '0 0 10px', fontSize: 12, color: 'var(--red)' }}>{err}</p>}
          <button type="submit" disabled={busy}
            style={{
              width: '100%', marginTop: 6, padding: 12, border: 0, borderRadius: 11,
              background: 'linear-gradient(135deg, var(--blue), var(--blue-deep))', color: '#fff',
              fontSize: 14, fontWeight: 700, cursor: busy ? 'progress' : 'pointer', opacity: busy ? 0.7 : 1,
            }}>{busy ? '확인 중…' : isLogin ? '로그인' : '가입하기'}</button>
        </form>

        {/* 소셜 로그인 (로그인 버튼 아래) */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '16px 0 12px', color: 'var(--ink-faint)', fontSize: 11 }}>
          <span style={{ flex: 1, height: 1, background: 'var(--line)' }} />또는<span style={{ flex: 1, height: 1, background: 'var(--line)' }} />
        </div>
        <div style={{ display: 'grid', gap: 8 }}>
          <button type="button" disabled={busy} onClick={() => socialDemo('카카오 사용자')} style={{ ...socialBtn, background: '#FEE500', color: '#191919' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" fill="#191919">
              <path d="M12 3C6.48 3 2 6.54 2 10.8c0 2.76 1.86 5.18 4.66 6.55-.15.53-.7 2.5-.8 2.9-.12.48.18.47.37.35.15-.1 2.4-1.63 3.37-2.28.66.1 1.34.15 2 .15 5.52 0 10-3.54 10-7.9S17.52 3 12 3z" />
            </svg>
            카카오로 계속하기
          </button>
          <button type="button" disabled={busy} onClick={() => socialDemo('네이버 사용자')} style={{ ...socialBtn, background: '#03C75A', color: '#fff' }}>
            <span style={{ fontFamily: 'system-ui, sans-serif', fontWeight: 900, fontSize: 14 }}>N</span>
            네이버로 계속하기
          </button>
        </div>

        <p style={{ margin: '16px 0 0', fontSize: 12.5, color: 'var(--ink-soft)', textAlign: 'center' }}>
          {isLogin ? '아직 계정이 없으신가요? ' : '이미 계정이 있으신가요? '}
          <button type="button" onClick={() => { setErr(''); setMode(isLogin ? 'signup' : 'login'); }} style={linkBtn}>
            {isLogin ? '회원가입' : '로그인'}
          </button>
        </p>
        {isLogin && (
          <p style={{ margin: '8px 0 0', textAlign: 'center' }}>
            <button type="button" onClick={() => setErr('비밀번호 찾기는 준비 중입니다.')}
              style={{ ...linkBtn, color: 'var(--ink-faint)', fontWeight: 500 }}>
              비밀번호를 잊으셨나요?
            </button>
          </p>
        )}
        </div>
      </div>
    </div>
  );
}

/* ---------- 마이페이지 · 실시간 AI 상담 ---------- */
