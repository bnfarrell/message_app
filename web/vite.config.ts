import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

const API = 'http://127.0.0.1:5000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: API, changeOrigin: true },
      '/a': { target: API, changeOrigin: true },
      '/ws': { target: API, ws: true, changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    environmentMatchGlobs: [
      ['src/index.css.test.ts', 'node'],
      ['src/api/types.generated.test.ts', 'node'],
    ],
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    css: false,
    // Unit and component tests only. tests/e2e/ belongs to Playwright.
    include: ['src/**/*.test.{ts,tsx}'],
    poolOptions: {
      // Node's own global `localStorage` (stable since Node 22) shadows jsdom's working
      // implementation: vitest only copies a jsdom window property onto the test global when
      // that key isn't already present on `global`, so Node's stub (which throws without
      // --localstorage-file) wins and jsdom's storage never gets installed. Disabling Node's
      // built-in lets vitest fall through to jsdom's real localStorage/sessionStorage.
      // Vitest's default pool is 'forks', not 'threads' -- set execArgv on both so the fix
      // holds regardless of which pool a future config change (or CLI flag) selects.
      threads: { execArgv: ['--no-experimental-webstorage'] },
      forks: { execArgv: ['--no-experimental-webstorage'] },
    },
  },
})
