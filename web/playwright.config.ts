import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false, // one server, one database — parallel specs would fight over seed state
  // fullyParallel:false only serialises tests *within* a file; separate spec files still get
  // separate workers. Presence is keyed by user id on the server, so two specs signed in as
  // Ava at the same time would move each other's presence entry between conversations.
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'line' : 'list',
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    ...devices['Desktop Chrome'],
  },
  webServer: [
    {
      // dev_start.py migrates and seeds only if empty, and runs the worker (START_WORKER=1).
      // `python` must be the project venv's — activate it before running the suite.
      command: 'python ../server/dev_start.py',
      url: 'http://127.0.0.1:5200/api/health',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: 'npm run dev',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
})
