import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const css = readFileSync(new URL('./index.css', import.meta.url), 'utf8')

const TOKENS = [
  'bg', 'bg2', 'nav', 'surface', 'surface2', 'border', 'border2', 'border3',
  'text', 'text2', 'text3', 'text4', 'accent', 'accentText', 'roomNum', 'sel',
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
  it('defines all 45 tokens in the dark (default) palette', () => {
    const dark = block(':root')
    for (const t of TOKENS) expect(dark, `--${t} missing from :root`).toContain(`--${t}:`)
  })

  it('redefines all 45 tokens in the light palette', () => {
    const light = block("[data-theme='light']")
    for (const t of TOKENS) expect(light, `--${t} missing from light`).toContain(`--${t}:`)
  })

  it('pins the approved accent and danger values in both palettes', () => {
    expect(block(':root')).toContain('--accent: #f0b323')
    expect(block("[data-theme='light']")).toContain('--accent: #f0b323')
    expect(block(':root')).toContain('--danger: #ff5d5d')
    expect(block("[data-theme='light']")).toContain('--danger: #dc2626')
  })

  it('has 45 tokens and no more, so a stray colour cannot sneak in', () => {
    const declaredTokens = (selector: string) =>
      [...new Set([...block(selector).matchAll(/--([a-zA-Z0-9]+):/g)].map((m) => m[1]))].sort()

    expect(declaredTokens(':root')).toEqual([...TOKENS].sort())
    expect(declaredTokens("[data-theme='light']")).toEqual([...TOKENS].sort())
  })
})
