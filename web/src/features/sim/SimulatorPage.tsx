/**
 * Placeholder — Task 20 replaces this with the real phone simulator.
 *
 * Exists only so `routes.tsx`'s `lazy(() => import('./features/sim/SimulatorPage'))` has a
 * module to resolve: Vite's import-analysis resolves a dynamic import's specifier for every
 * module transform (dev server and Vitest alike), regardless of whether the surrounding
 * `import.meta.env.DEV` ternary would actually execute it — that folding only happens in a
 * production build. Without this file, `routes.tsx` fails to load at all, dev build included.
 */
export default function SimulatorPage() {
  return null
}
