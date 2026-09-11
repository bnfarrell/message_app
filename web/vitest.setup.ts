import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'

/**
 * Fake timers must not outlive the test that installed them (ruling D92).
 *
 * A test that times out *inside* a `try` never reaches its own `finally`, so a `vi.useFakeTimers()`
 * it installed leaks into every later test in the same file. Those victims then hang on a clock
 * nobody advances and report only "Test timed out", which names neither the cause nor the culprit
 * — one bad test cost this project 13 such failures. Restoring here bounds the damage to the test
 * that actually hung.
 *
 * `useRealTimers()` on a run that never faked them is a no-op, so this is free for the other 45
 * files.
 */
afterEach(() => {
  vi.useRealTimers()
})
