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
    // Dev-only: forward API calls to the local backend so the SPA's relative
    // /api/v1/* requests reach FastAPI (prod serves both same-origin via Caddy).
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
})
