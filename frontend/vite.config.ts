import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Dev-only: forward API calls to the backend so the SPA's relative
    // /api/v1/* requests reach FastAPI (prod serves both same-origin via Caddy).
    // Under `just up` the frontend runs in its own container, so the target must
    // be the compose service name `backend` — `localhost` there resolves to the
    // frontend container itself (nothing on :8000 → ECONNREFUSED, and the backend
    // never sees the request). Override with VITE_API_PROXY_TARGET when running
    // `pnpm dev` on the host (e.g. http://localhost:8000).
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET ?? 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
})
