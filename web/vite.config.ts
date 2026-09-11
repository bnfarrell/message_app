import { spawnSync } from 'node:child_process'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

const API = 'http://127.0.0.1:5000'

/**
 * True only if the currently-running Node binary accepts `flag` as a CLI argument.
 * Any other outcome (unrecognised flag, or the spawn itself failing for an unrelated
 * reason) is treated as "unsupported" rather than thrown, and nothing is printed --
 * an unsupported flag is an expected, silent case here, not an error.
 */
function nodeAcceptsFlag(flag: string): boolean {
  try {
    return spawnSync(process.execPath, [flag, '-e', ''], { stdio: 'ignore' }).status === 0
  } catch {
    return false
  }
}

// Node 25+ enables a native `localStorage`/`sessionStorage` global by default (it was
// opt-in behind --experimental-webstorage from Node 22.4 through 24.x). That global shadows
// jsdom's working implementation: vitest only copies a jsdom `window` property onto the test
// global when that key isn't already present on `global`, so Node's stub (which throws
// without --localstorage-file) wins and jsdom's storage never gets installed.
//
// The flag to disable it was renamed from --no-experimental-webstorage to --no-webstorage
// partway through Node 25, and this project's floor is Node 20 (see package.json engines),
// which has no such flag at all -- passing an unrecognised flag makes every worker's `node`
// invocation exit immediately with "bad option", a total suite outage, not a test failure.
// So: probe for both spellings and use whichever this Node build actually accepts (if any),
// instead of hard-coding one.
const webStorageFlag = ['--no-webstorage', '--no-experimental-webstorage'].find(nodeAcceptsFlag)
const webStorageExecArgv = webStorageFlag ? [webStorageFlag] : []

export default defineConfig({
  plugins: [react()],
  server: {
    // Bind IPv4 explicitly. Vite's default host resolves per-OS, and on Windows it
    // can end up listening on [::1] only -- which makes http://127.0.0.1:5173
    // refuse connections while http://localhost:5173 works, or vice versa,
    // depending on how the browser resolves the name. Pinning it removes that coin flip.
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': { target: API, changeOrigin: true },
      // A string key is matched by prefix, and '/app/inbox'.startsWith('/a') is true --
      // every hard navigation to an /app/* route was being proxied to Flask instead of
      // served by Vite. A key starting with '^' is a RegExp instead: '^/a/' requires the
      // slash right after '/a', so it still matches the asset short-link route
      // (GET /a/<short_code>) without also matching /app/*.
      '^/a/': { target: API, changeOrigin: true },
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
      // See webStorageExecArgv above. Empty on a Node that doesn't need or support the flag
      // (e.g. this project's Node 20 floor). Vitest's default pool is 'forks', not 'threads' --
      // set execArgv on both so the fix holds regardless of which pool a future config change
      // (or CLI flag) selects.
      threads: { execArgv: webStorageExecArgv },
      forks: { execArgv: webStorageExecArgv },
    },
  },
})
