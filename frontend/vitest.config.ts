import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['src/test-setup.ts'],
    // Playwright owns e2e/*.spec.ts (its own test/expect, a real browser, a live backend) —
    // vitest's default include glob would otherwise also try to run them under jsdom.
    exclude: ['**/node_modules/**', '**/dist/**', 'e2e/**'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/**/*.{ts,vue}'],
      exclude: ['src/types/**', 'src/main.ts', 'src/shims.d.ts', 'src/locales/**'],
      thresholds: { lines: 80, functions: 80, branches: 75, statements: 80 },
    },
  },
})
