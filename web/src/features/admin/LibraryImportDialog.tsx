import { useState } from 'react'
import { useChecklistLibrary, useImportChecklist } from '../../api/hooks/checklists'
import { useDepartments } from '../../api/hooks/users'
import type { ChecklistLibraryEntryOut, ChecklistTemplateOut } from '../../api/types'
import { Badge, Button, Dialog, Spinner } from '../../components/ui'
import { KIND_LABELS } from '../checklists/labels'
import { SELECT } from './ItemListEditor'

function summary(entry: ChecklistLibraryEntryOut): string {
  const categories = entry.categories.map((c) => c.name).join(' · ')
  const items = `${entry.itemCount} item${entry.itemCount === 1 ? '' : 's'}`
  return categories ? `${categories} — ${items}` : items
}

/**
 * Import From Library (checklist structure spec §4.1): pick a starter checklist and a department;
 * the copy arrives unscheduled and `onImported` opens it in the editor to review and schedule.
 */
export function LibraryImportDialog({ open, onClose, onImported }: {
  open: boolean
  onClose: () => void
  onImported: (template: ChecklistTemplateOut) => void
}) {
  const { data: entries, isPending, error } = useChecklistLibrary(open)
  const { data: departments } = useDepartments()
  const importChecklist = useImportChecklist()
  const [key, setKey] = useState('')
  const [departmentId, setDepartmentId] = useState('')

  function close() {
    importChecklist.reset()
    setKey('')
    setDepartmentId('')
    onClose()
  }

  function choose(entry: ChecklistLibraryEntryOut) {
    setKey(entry.key)
    // Suggest the first department of the entry's type; the admin can pick another.
    const match = (departments ?? []).find((d) => d.type === entry.departmentType)
    setDepartmentId(match?.id ?? '')
  }

  return (
    <Dialog
      open={open}
      onClose={close}
      title="Import from library"
      wide
      footer={
        <>
          <Button onClick={close}>Cancel</Button>
          <Button
            variant="primary"
            disabled={!key || !departmentId}
            loading={importChecklist.isPending}
            onClick={() =>
              importChecklist.mutate({ key, departmentId }, {
                onSuccess: (template) => {
                  importChecklist.reset()
                  setKey('')
                  setDepartmentId('')
                  onImported(template)
                },
              })
            }
          >
            Import
          </Button>
        </>
      }
    >
      <p className="text-xs text-text3">
        A starter checklist is copied into this property without a schedule. Review it, then pick
        Weekly or On demand.
      </p>
      {isPending ? (
        <Spinner />
      ) : error ? (
        <p role="alert" className="text-sm text-dangerText">{error.message}</p>
      ) : (
        <fieldset className="flex flex-col gap-2">
          <legend className="sr-only">Starter checklists</legend>
          {entries.map((entry) => (
            <label key={entry.key} className="flex items-start gap-2 rounded border border-border2 p-2 text-sm">
              <input type="radio" name="library-entry" className="mt-1" checked={key === entry.key}
                     onChange={() => choose(entry)} />
              <span className="flex flex-col gap-1">
                <span className="flex items-center gap-2 font-semibold">
                  {entry.name}
                  {entry.kind === 'readings' ? <Badge tone="note">{KIND_LABELS.readings}</Badge> : null}
                </span>
                <span className="text-xs text-text3">{summary(entry)}</span>
              </span>
            </label>
          ))}
        </fieldset>
      )}
      <div>
        <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-text3" htmlFor="library-dept">
          Department
        </label>
        <select id="library-dept" className={SELECT} value={departmentId}
                onChange={(e) => setDepartmentId(e.target.value)}>
          <option value="">Choose a department</option>
          {(departments ?? []).map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
      </div>
      {importChecklist.error ? (
        <p role="alert" className="text-sm text-dangerText">{importChecklist.error.message}</p>
      ) : null}
    </Dialog>
  )
}
