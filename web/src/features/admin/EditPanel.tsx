import { useState, type ReactNode } from 'react'
import { Button } from '../../components/ui'

/**
 * `subjectId` is required, and it is the only reason this component can be trusted with a
 * destructive control.
 *
 * The panel is rendered as `{draft ? <EditPanel …/> : null}` on every admin screen, and every
 * `open()` replaces the draft without passing through `null` — so the element type and position
 * are unchanged, React reconciles instead of remounting, and `confirming` survives a change of
 * subject. Left alone, a Delete armed on one record stays armed over the next record the admin
 * opens, one click from deleting something they never asked about. The refusal paths make that
 * routine rather than rare: Departments and resolution categories both answer a delete with a 409
 * while the record is referenced, so an admin is *expected* to arm, be refused, and move on.
 *
 * The nastier route is the one that looks safe. Arm the confirmation, then press "New …": the
 * delete controls disappear, because `onDelete` is undefined for a record that does not exist yet,
 * and the admin reasonably reads that as the confirmation having been dismissed. It has not.
 * Opening any saved record brings it back, armed.
 *
 * Resetting here rather than with a `key` at each call site is deliberate. A key is an invisible
 * convention that nothing enforces and every future screen must remember, and it throws away the
 * whole panel subtree — scroll position and any child state with it — to clear one boolean. A
 * required prop is checked by the compiler.
 */
export function EditPanel({
  subjectId,
  title,
  subtitle,
  children,
  onSave,
  onDelete,
  onCancel,
  saving,
  error,
}: {
  /** Identifies the record on screen. Any change disarms a pending delete confirmation. */
  subjectId: string
  title: string
  subtitle?: string
  children: ReactNode
  onSave: () => void
  onDelete?: () => void
  onCancel: () => void
  saving?: boolean
  error?: string | null
}) {
  const [confirming, setConfirming] = useState(false)
  const [armedFor, setArmedFor] = useState(subjectId)

  // Render-phase reset (React's documented "adjusting state when a prop changes"), not an effect:
  // an effect would leave one committed frame in which Confirm is on screen for the new subject,
  // and that frame is exactly long enough to click.
  if (subjectId !== armedFor) {
    setArmedFor(subjectId)
    setConfirming(false)
  }

  return (
    <aside className="w-[340px] flex-none overflow-y-auto border-l border-border bg-bg2 p-4">
      <header className="mb-3">
        <h2 className="text-sm font-bold">{title}</h2>
        {subtitle ? <p className="text-xs text-text3">{subtitle}</p> : null}
      </header>

      {error ? (
        <p role="alert" className="mb-3 rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
          {error}
        </p>
      ) : null}

      <div className="flex flex-col gap-3">{children}</div>

      <footer className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="primary" loading={saving} onClick={onSave}>
          Save
        </Button>
        <Button onClick={onCancel}>Cancel</Button>
        {onDelete ? (
          confirming ? (
            <>
              <span className="w-full text-xs text-dangerText">
                Delete this? This cannot be undone.
              </span>
              <Button variant="danger" onClick={onDelete}>
                Confirm
              </Button>
              <Button onClick={() => setConfirming(false)}>Keep</Button>
            </>
          ) : (
            <Button variant="ghost" className="ml-auto text-dangerText" onClick={() => setConfirming(true)}>
              Delete
            </Button>
          )
        ) : null}
      </footer>
    </aside>
  )
}
