import { ApiError } from './client'

/** One Pydantic error, as `app/api/_util.parse_body` forwards it (`e.errors(include_url=False)`). */
type PydanticError = { loc?: unknown[]; msg?: string }

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
 *   a reason **code**, not a sentence — a form maps it to its own wording.
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
      Object.entries(details as Record<string, unknown>).map(([k, v]) => [k, String(v)]),
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
