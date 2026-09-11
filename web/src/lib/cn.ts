import { twMerge } from 'tailwind-merge'

/**
 * Joins class parts AND resolves Tailwind conflicts, last one wins.
 *
 * The plain-join version of this (ruling D69) silently dropped colour overrides: when a
 * `className` passed into a component collided with the component's own base class, the
 * class-string order was irrelevant and CSS source order decided — which here means the
 * order of the token array in `tailwind.config.js`. `tsc`, `npm run lint` and the whole
 * test suite all passed over the dead override, and the workaround for it (`!bg-noteBg`)
 * has already caused one accessibility defect by beating a `focus:` rule.
 *
 * tailwind-merge treats `!important` as its own conflict group, so the one `!`-prefixed
 * call site in the client (Composer's note mode) is untouched by this and still wins the
 * cascade the way it did before.
 */
export function cn(...parts: (string | false | null | undefined)[]): string {
  return twMerge(parts)
}
