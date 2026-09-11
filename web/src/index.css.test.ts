import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const css = readFileSync(new URL('./index.css', import.meta.url), 'utf8')

const TOKENS = [
  'bg', 'bg2', 'nav', 'surface', 'surface2', 'border', 'border2', 'border3',
  'text', 'text2', 'text3', 'text4', 'accent', 'accentText', 'roomNum', 'sel',
  'navText', 'navTextMuted', 'navSection', 'navActiveBg', 'navActiveText', 'navBorder',
  'navFocus',
  'outBg', 'outText', 'autoBg', 'autoText', 'autoBorder',
  'noteBg', 'noteBorder', 'noteText', 'noteIcon',
  'okBg', 'okText', 'okBorder', 'okBtn', 'okBtnText', 'okBanner',
  'warnBg', 'warnText', 'dangerBg', 'dangerText', 'danger',
  'presenceBg', 'presenceText', 'presenceAv',
  'avMuted', 'avText', 'tagBg', 'tagText', 'timerDoneBg', 'timerDoneText',
]

function block(selector: string): string {
  const start = css.indexOf(selector)
  expect(start, `${selector} block is missing`).toBeGreaterThan(-1)
  return css.slice(css.indexOf('{', start), css.indexOf('}', start))
}

describe('design tokens', () => {
  it('defines every token in the dark (default) palette', () => {
    const dark = block(':root')
    for (const t of TOKENS) expect(dark, `--${t} missing from :root`).toContain(`--${t}:`)
  })

  it('redefines every token in the light palette', () => {
    const light = block("[data-theme='light']")
    for (const t of TOKENS) expect(light, `--${t} missing from light`).toContain(`--${t}:`)
  })

  it('pins the approved accent and danger values in both palettes', () => {
    expect(block(':root')).toContain('--accent: #4f8fd4')
    expect(block("[data-theme='light']")).toContain('--accent: #2563eb')
    expect(block(':root')).toContain('--danger: #f26d6d')
    expect(block("[data-theme='light']")).toContain('--danger: #dc2626')
  })

  // Relative luminance, WCAG 2.x. Kept here rather than imported so the assertion below is
  // readable on its own: these are the pairs the navy rail actually ships.
  function luminance(hex: string): number {
    const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    const linear = channels.map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
    return 0.2126 * linear[0]! + 0.7152 * linear[1]! + 0.0722 * linear[2]!
  }

  function contrast(a: string, b: string): number {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number]
    return (hi + 0.05) / (lo + 0.05)
  }

  function value(selector: string, token: string): string {
    const match = block(selector).match(new RegExp(`--${token}: (#[0-9a-f]{6})`))
    expect(match, `--${token} missing from ${selector}`).not.toBeNull()
    return match![1]!
  }

  it.each([':root', "[data-theme='light']"])(
    'keeps every rail foreground legible on the navy rail in %s',
    (theme) => {
      const rail = value(theme, 'nav')
      // 4.5:1 is the text minimum. The rail's labels are 13-14px, so none of them qualify
      // for the 3:1 large-text allowance.
      for (const token of ['navText', 'navTextMuted', 'navSection']) {
        expect(contrast(value(theme, token), rail), `--${token} on --nav`).toBeGreaterThanOrEqual(4.5)
      }
      // The active pill is a UI component against the rail (3:1) carrying text (4.5:1).
      expect(contrast(value(theme, 'navActiveBg'), rail), '--navActiveBg on --nav')
        .toBeGreaterThanOrEqual(3)
      expect(contrast(value(theme, 'navActiveText'), value(theme, 'navActiveBg')),
        '--navActiveText on --navActiveBg').toBeGreaterThanOrEqual(4.5)
      // A focus ring must be visible against what it sits on (3:1). --accent alone is
      // 3.33:1 on the light rail, which is why --navFocus exists.
      expect(contrast(value(theme, 'navFocus'), rail), '--navFocus on --nav')
        .toBeGreaterThanOrEqual(3)
    },
  )

  it.each([':root', "[data-theme='light']"])(
    'keeps --surface above --surface2 in lightness in %s, so a raised tile never inverts',
    (theme) => {
      // Composer's mode tabs render the active tab as bg-surface inside a bg-surface2 track.
      // When the two swap order between themes the same markup reads as a raised pill in one
      // and an inset well in the other (ruling D74).
      expect(luminance(value(theme, 'surface'))).toBeGreaterThan(luminance(value(theme, 'surface2')))
    },
  )

  it('has exactly this set and no more, so a stray colour cannot sneak in', () => {
    const declaredTokens = (selector: string) =>
      [...new Set([...block(selector).matchAll(/--([a-zA-Z0-9]+):/g)].map((m) => m[1]))].sort()

    expect(declaredTokens(':root')).toEqual([...TOKENS].sort())
    expect(declaredTokens("[data-theme='light']")).toEqual([...TOKENS].sort())
  })
})
