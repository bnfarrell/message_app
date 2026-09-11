import { describe, expect, it } from 'vitest'
import { cn } from './cn'

describe('cn', () => {
  it('joins truthy parts with a single space', () => {
    expect(cn('a', 'b')).toBe('a b')
  })

  it('drops false, null and undefined so conditionals read inline', () => {
    expect(cn('a', false, null, undefined, 'b')).toBe('a b')
  })

  it('returns an empty string when everything is falsy', () => {
    expect(cn(false, undefined)).toBe('')
  })

  it('lets a later colour override beat the base class it collides with', () => {
    // The reason this matters (D69): a plain join leaves both classes in the attribute and
    // CSS source order decides, which is the order of the token array in tailwind.config.js.
    // `bg-nav` is declared before `bg-surface2` there, so the override used to lose silently.
    expect(cn('bg-surface2 px-3', 'bg-nav')).toBe('px-3 bg-nav')
    expect(cn('text-text3 hover:text-text', 'text-dangerText')).toBe(
      'hover:text-text text-dangerText',
    )
  })

  it('leaves an !important override and its base class both standing', () => {
    // tailwind-merge keys the conflict group on the important modifier, so Composer's note
    // mode keeps winning through `!important` exactly as it did before — and its
    // focus:!border-accent is not swallowed by the base focus:border-accent either.
    expect(cn('border-border3 focus:border-accent', '!border-noteBorder focus:!border-accent'))
      .toBe('border-border3 focus:border-accent !border-noteBorder focus:!border-accent')
  })

  it('does not touch a class it does not recognise', () => {
    expect(cn('shadow-[inset_3px_0_0_var(--accent)]', 'rounded-card')).toBe(
      'shadow-[inset_3px_0_0_var(--accent)] rounded-card',
    )
  })
})
