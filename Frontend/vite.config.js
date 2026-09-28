import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
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
