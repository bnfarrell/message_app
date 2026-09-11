import { useState, type ReactNode } from 'react'
import { Button } from '../../components/ui'

export function EditPanel({
  title,
  subtitle,
  children,
  onSave,
  onDelete,
  onCancel,
  saving,
  error,
}: {
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
