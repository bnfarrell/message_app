/**
 * The one name under which the active property is stored, plus the one way to clear it.
 *
 * It lives in its own module because the three places that need it cannot otherwise share it:
 * `SessionContext` reads and writes it, `useLogout` clears it on an explicit sign-out, and
 * `RequireAuth` clears it on a silent session loss — and `SessionContext` already imports
 * `hooks/auth`, so holding the constant in `SessionContext` and importing it back would be a
 * cycle. A duplicated string literal in three files is the alternative, and it was already
 * duplicated in two.
 *
 * Every access is wrapped: private browsing and blocked site data both throw on `localStorage`.
 */
export const ACTIVE_PROPERTY_KEY = 'activePropertyId'

/**
 * The stored property is this user's choice, not the machine's. On a shared front-desk terminal
 * the next person to sign in would otherwise land on it, if they happen to hold a membership
 * there too.
 */
export function clearActivePropertyId(): void {
  try {
    localStorage.removeItem(ACTIVE_PROPERTY_KEY)
  } catch {
    /* private mode / blocked storage: there was nothing stored to clear */
  }
}
