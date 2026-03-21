import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for Monocle E2E tests.
 * Run from the repo root: npm run test:e2e
 *
 * Prerequisites:
 *   1.  uv run python -m monocle serve   (or dev)   → http://127.0.0.1:8000
 *   2.  cd frontend && npm run dev                  → http://localhost:5173
 *   3.  npm run test:e2e                            (from repo root)
 */
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,          // Tests share live server state
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? 'github' : 'list',

  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    // Generous timeouts for a local LLM-backed server
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Timeout per test — generous because LLM round-trips can be slow
  timeout: 60_000,
});
