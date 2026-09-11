import { ApiError } from './client'

/** One Pydantic error, as `app/api/_util.parse_body` forwards it (`e.errors(include_url=False)`). */
type PydanticError = { loc?: unknown[]; msg?: string }

/**
 * Human copy for the reason codes the object shape carries (ruling D93).
 *
 * The two shapes differ in what the value *means*, not only in structure: the array shape's `msg`
 * is already an English sentence, while the object shape's value is a bare code meant to be worded
 * by whoever renders it. `required` reads acceptably raw; `invalid_phone_number` under a Phone box
 * does not. Mapping here rather than in each screen means every current and future form gets the
 * same wording for the same failure, and a new form gets it for free.
 *
 * These are every code `server/app/` raises today — `app/domain/_patch.py` (`required`),
 * `app/domain/guests.py` (`invalid_phone_number`) and `app/domain/properties.py`
 * (`invalid_timezone`). An unlisted code falls through **verbatim** rather than being swallowed or
 * replaced by a generic apology: a code on screen is ugly but actionable, and it names the gap.
 */
const REASON_COPY: Record<string, string> = {
  required: 'This field is required.',
  invalid_phone_number: 'Enter a valid phone number, for example +1 555 012 3456.',
  invalid_timezone: 'Not a recognised IANA time zone.',
}

/**
 * Maps a 400's `details` onto the form inputs it names, so a failure lands on the field the admin
 * typed in rather than only in a banner.
 *
 * The server has **two** shapes for `details` and neither is going away. A1 left them alone
 * deliberately: unifying them means changing `parse_body` for every endpoint in the product, and
 * it interacts with a separate unfixed defect there. So this normaliser is the contract.
 *
 * - `app/api/_util.parse_body` forwards Pydantic's error **array**:
 *   `[{ loc: ["smsNumber"], msg: "String should have at most 32 characters", type, ctx, input }]`.
 *   The field is `loc`'s last element; the message is `msg`.
 * - `app/domain/_patch.patch_changes` and the domain validators raise an **object** keyed by field:
 *   `{ "escalationMinutes": "required", "smsNumber": "invalid_phone_number" }`. The value there is
 *   a reason **code**, not a sentence. `REASON_COPY` below turns it into one, so a form can
 *   render what it gets either way.
 *
 * Both key on the camelCase name the client sent, so the result can be indexed by the form's own
 * field names either way. A key the form has no input for is simply never looked up; the panel's
 * banner still carries the top-level `message`, so nothing is lost.
 *
 * `input` is deliberately never read. It echoes the admin's raw typing back, which tells them
 * nothing they cannot already see in the box they typed it into.
 */
export function fieldErrors(error: unknown): Record<string, string> {
  const details = error instanceof ApiError ? error.details : undefined
  if (!details || typeof details !== 'object') return {}

  if (!Array.isArray(details)) {
    return Object.fromEntries(
      Object.entries(details as Record<string, unknown>).map(([k, v]) => {
        const code = String(v)
        return [k, REASON_COPY[code] ?? code]
      }),
    )
  }

  const out: Record<string, string> = {}
  for (const item of details as PydanticError[]) {
    // `loc` ends in an array index for a list field's nth element, which names no input. Such an
    // error is left out rather than keyed under a number; the banner still reports it.
    const field = item.loc?.[item.loc.length - 1]
    if (typeof field === 'string' && item.msg && !(field in out)) out[field] = item.msg
  }
  return out
}
