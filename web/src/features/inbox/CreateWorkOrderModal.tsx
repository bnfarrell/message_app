import { useEffect, useState } from 'react'
import { useCreateWorkOrder, useWorkOrderPrefill } from '../../api/hooks/workOrders'
import { useDepartments, useStaff } from '../../api/hooks/users'
import type { CreateWorkOrder, LocationType, Priority, WorkOrderType } from '../../api/types'
import { Button, Dialog, Input, Spinner, Textarea, useToast } from '../../components/ui'

const TYPES: WorkOrderType[] = ['maintenance', 'housekeeping', 'guest_request', 'pm', 'other']
const PRIORITIES: Priority[] = ['low', 'normal', 'high', 'urgent']
const LOCATION_TYPES: LocationType[] = ['room', 'public_area', 'equipment', 'other']

// A work order raised from the board has no suggestion to seed it. `sourceConversationId` is
// absent rather than null, so the POST body omits it entirely.
const BLANK: CreateWorkOrder = {
  title: '',
  description: '',
  type: 'maintenance',
  priority: 'normal',
  locationType: 'room',
  locationRef: '',
  departmentId: null,
  assignedUserId: null,
  dueAt: null,
}

const FIELD = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT =
  'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

export function CreateWorkOrderModal({
  conversationId,
  open,
  onClose,
}: {
  /** Absent when the work order is raised standalone, from the board. */
  conversationId?: string
  open: boolean
  onClose: () => void
}) {
  const prefill = useWorkOrderPrefill(open ? conversationId : undefined)
  const create = useCreateWorkOrder()
  const { data: departments } = useDepartments()
  const { data: staff } = useStaff()
  const toast = useToast()
  const [form, setForm] = useState<CreateWorkOrder | null>(() =>
    conversationId ? null : { ...BLANK },
  )

  // Seed the form once the suggestion lands; the agent owns it from then on. With no
  // conversation there is no suggestion to wait for, so the form opens blank immediately.
  useEffect(() => {
    if (form || !open) return
    if (!conversationId) {
      setForm({ ...BLANK })
    } else if (prefill.data) {
      setForm({
        title: prefill.data.title,
        description: prefill.data.description,
        type: prefill.data.type,
        priority: prefill.data.priority,
        locationType: prefill.data.locationType,
        locationRef: prefill.data.locationRef,
        departmentId: prefill.data.departmentId,
        assignedUserId: null,
        dueAt: null,
        sourceConversationId: prefill.data.sourceConversationId,
        sourceMessageId: prefill.data.sourceMessageId,
      })
    }
  }, [prefill.data, form, open, conversationId])

  function set<K extends keyof CreateWorkOrder>(key: K, value: CreateWorkOrder[K]) {
    setForm((current) => (current ? { ...current, [key]: value } : current))
  }

  // Any non-success dismissal (Cancel, Escape, backdrop) drops the edited draft so a
  // reopen re-seeds from a fresh prefill rather than showing a stale session's edits.
  function handleClose() {
    setForm(null)
    onClose()
  }

  function submit() {
    if (!form || !form.title.trim()) return
    create.mutate(form, {
      onSuccess: (created) => {
        toast(`Work order #${created.id} created`)
        handleClose()
      },
    })
  }

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      title="Create work order"
      wide
      footer={
        <>
          <Button onClick={handleClose}>Cancel</Button>
          <Button variant="primary" loading={create.isPending} onClick={submit}>
            Create
          </Button>
        </>
      }
    >
      {!form ? (
        <div className="grid place-items-center py-8">
          <Spinner />
        </div>
      ) : (
        <>
          {create.error ? (
            <p role="alert" className="rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
              {create.error.message}
            </p>
          ) : null}

          {prefill.data?.guestName ? (
            <p className="text-xs text-text3">
              Pre-filled from {prefill.data.guestName}&rsquo;s message.
            </p>
          ) : null}

          <div>
            <label className={FIELD} htmlFor="wo-title">Title</label>
            <Input id="wo-title" value={form.title} onChange={(e) => set('title', e.target.value)} />
          </div>

          <div>
            <label className={FIELD} htmlFor="wo-desc">Description</label>
            <Textarea
              id="wo-desc"
              rows={4}
              value={form.description ?? ''}
              onChange={(e) => set('description', e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={FIELD} htmlFor="wo-type">Type</label>
              <select id="wo-type" className={SELECT} value={form.type}
                      onChange={(e) => set('type', e.target.value as WorkOrderType)}>
                {TYPES.map((t) => (
                  <option key={t} value={t}>{t.replace('_', ' ')}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={FIELD} htmlFor="wo-priority">Priority</label>
              <select id="wo-priority" className={SELECT} value={form.priority}
                      onChange={(e) => set('priority', e.target.value as Priority)}>
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={FIELD} htmlFor="wo-dept">Department</label>
              <select id="wo-dept" className={SELECT} value={form.departmentId ?? ''}
                      onChange={(e) => set('departmentId', e.target.value || null)}>
                <option value="">—</option>
                {(departments ?? []).map((d) => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={FIELD} htmlFor="wo-assignee">Assignee</label>
              <select id="wo-assignee" className={SELECT} value={form.assignedUserId ?? ''}
                      onChange={(e) => set('assignedUserId', e.target.value || null)}>
                <option value="">Unassigned</option>
                {(staff ?? []).map((s) => (
                  <option key={s.id} value={s.id}>{s.firstName} {s.lastName}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={FIELD} htmlFor="wo-location-type">Location type</label>
              <select id="wo-location-type" className={SELECT} value={form.locationType ?? 'room'}
                      onChange={(e) => set('locationType', e.target.value as LocationType)}>
                {LOCATION_TYPES.map((l) => (
                  <option key={l} value={l}>{l.replace('_', ' ')}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={FIELD} htmlFor="wo-location">Location</label>
              <Input
                id="wo-location"
                value={form.locationRef ?? ''}
                onChange={(e) => set('locationRef', e.target.value)}
              />
            </div>
          </div>
        </>
      )}
    </Dialog>
  )
}
