import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    // PWA: 빌드 시 manifest·sw.js 를 생성한다. 설계는 Docs/reports/PWA_PLAN.md.
    VitePWA({
      // 새 배포(main 병합 → 재빌드)가 감지되면 사용자 조작 없이 SW 를 교체한다.
      registerType: 'autoUpdate',
      injectRegister: 'auto',
      // public/ 파일은 아래 globPatterns 로 이미 precache 되므로 중복 등록하지 않는다.
      includeManifestIcons: false,
      manifest: {
        name: '창업ON',
        short_name: '창업ON',
        description: '흩어진 청년 창업 지원 공고와 세무 업무를 한 곳에서 - 창업ON',
        lang: 'ko',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        // 데스크톱 Chrome·Edge 설치 앱은 OS 타이틀바 대신 창 버튼만 앱 우상단에 겹쳐 표시한다.
        // 미지원 환경(모바일 등)은 위 standalone 으로 표시된다.
        display_override: ['window-controls-overlay'],
        // 상단 상태바·타이틀바가 화면과 이어져 보이도록 앱 배경(--ground)과 같은 색을 쓴다.
        theme_color: '#f4f6fd',
        background_color: '#f4f6fd',
        icons: [
          { src: 'pwa-192x192.png?v=2', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png?v=2', sizes: '512x512', type: 'image/png' },
          { src: 'maskable-icon-512x512.png?v=2', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // 빌드 산출물만 precache 한다. /api 응답은 사용자별 데이터라 캐시하지 않는다.
        globPatterns: ['**/*.{js,css,html,svg,png,ico}'],
        navigateFallback: '/index.html',
        // API·발표자료(Slidev) 요청을 SW 가 index.html 로 가로채지 않게 한다.
        navigateFallbackDenylist: [/^\/api\//, /^\/ppt/],
      },
    }),
  ],
  server: {
    port: 5173,
    open: true,
    proxy: {
      // 백엔드(Django) 연동: /api/* → http://localhost:8000/*
      // Backend는 /api 접두사 없이 라우트를 마운트하므로 rewrite로 접두사를 벗긴다.
      // compose 개발 모드(frontend-dev)에서는 VITE_PROXY_TARGET=http://backend:8000 으로 바꾼다.
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
});
