import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { charCount, isGsm7, segmentCount } from './segments'

/**
 * Ruling D89. This module is a deliberate line-for-line port of
 * server/app/domain/sms.py — the composer needs a per-keystroke count with no
 * network round trip — so nothing but this fixture stops the two drifting.
 * server/tests/test_sms.py asserts the same file; if either side moves, exactly
 * one suite goes red and names the case.
 *
 * `characters` is code points (charCount, `[...body].length`), `segments` is
 * septets or UTF-16 code units (`body.length`). For a non-BMP character those
 * differ, which is what the emoji-crosses-* cases exist to pin.
 */

// dirname(fileURLToPath(...)) rather than new URL('.', import.meta.url).pathname:
// on Windows the latter's pathname ("/C:/Users/...") makes node:path's join()
// prepend the current drive again. Same reasoning as types.generated.test.ts.
const here = dirname(fileURLToPath(import.meta.url))
const fixture = join(here, '..', '..', '..', 'fixtures', 'sms-segments.json')

interface Case {
  name: string
  why: string
  body: string
  isGsm7: boolean
  segments: number
  characters: number
}

const cases = (JSON.parse(readFileSync(fixture, 'utf8')) as { cases: Case[] }).cases

describe('shared SMS segment vectors', () => {
  it.each(cases.map((c) => [c.name, c] as const))('%s', (_name, c) => {
    expect(isGsm7(c.body), c.why).toBe(c.isGsm7)
    expect(segmentCount(c.body), c.why).toBe(c.segments)
    expect(charCount(c.body), c.why).toBe(c.characters)
  })

  it('covers the boundaries, so the guard above cannot go vacuous', () => {
    const names = new Set(cases.map((c) => c.name))
    for (const required of [
      'empty', 'gsm7-160', 'gsm7-161', 'gsm7-306', 'gsm7-307',
      'gsm7-extension-crosses-160', 'gsm7-extension-crosses-153',
      'ucs2-70', 'ucs2-71', 'ucs2-134', 'ucs2-135',
      'emoji-alone', 'emoji-crosses-70', 'emoji-crosses-67',
    ]) {
      expect(names, `${required} is missing from the shared fixture`).toContain(required)
    }
  })
})
