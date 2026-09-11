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
    environmentMatchGlobs: [['src/index.css.test.ts', 'node']],
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    css: false,
    // Unit and component tests only. tests/e2e/ belongs to Playwright.
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
