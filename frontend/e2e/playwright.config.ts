import { defineConfig, devices } from '@playwright/test'
import { fileURLToPath } from 'node:url'

const __dirname = fileURLToPath(new URL('.', import.meta.url))

/** The four reference widths from the design source, each in light + dark. */
const VIEWPORTS: Record<string, { width: number; height: number }> = {
  '320': { width: 320, height: 720 },
  '768': { width: 768, height: 1024 },
  '1024': { width: 1024, height: 768 },
  '1440': { width: 1440, height: 900 },
}
const COLOR_SCHEMES = ['light', 'dark'] as const

export default defineConfig({
  testDir: '.',
  outputDir: './test-results',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['html', { outputFolder: './playwright-report', open: 'never' }]],
  globalSetup: './global-setup.ts',
  use: {
    baseURL: 'http://localhost:5173',
    storageState: `${__dirname}/.auth/admin-storage.json`,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'pnpm dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    cwd: '..',
  },
  projects: Object.entries(VIEWPORTS).flatMap(([width, viewport]) =>
    COLOR_SCHEMES.map((colorScheme) => ({
      name: `${width}-${colorScheme}`,
      use: {
        ...devices['Desktop Chrome'],
        viewport,
        colorScheme,
      },
    })),
  ),
})
