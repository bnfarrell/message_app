import { useRef, useState } from 'react'
import { useUploadWorkOrderPhoto } from '../../api/hooks/workOrders'
import type { WorkOrderPhotoOut } from '../../api/types'
import { fieldErrors } from '../../api/fieldErrors'
import { formatClock } from '../../lib/time'

const MAX_BYTES = 8 * 1024 * 1024 // server's work_orders.MAX_PHOTO_BYTES
const ACCEPTED = ['image/jpeg', 'image/png', 'image/webp']
const KIND_LABEL: Record<'before' | 'after', string> = { before: 'Before', after: 'After' }

export function PhotoPanel({ workOrderId, photos }: { workOrderId: string; photos: WorkOrderPhotoOut[] }) {
  const [kind, setKind] = useState<'before' | 'after'>('before')
  const [picking, setPicking] = useState(false)
  const [clientError, setClientError] = useState<string | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const upload = useUploadWorkOrderPhoto(workOrderId)

  function pick() {
    setClientError(null)
    setPicking(true)
  }

  function onFile(file: File | undefined) {
    if (!file) return
    // Fast client-side check so a slow upload is not how the guest finds out it will fail —
    // the server re-checks both regardless (it sniffs bytes, not the declared type).
    if (!ACCEPTED.includes(file.type)) {
      setClientError('Only JPEG, PNG or WebP photos are accepted.')
      return
    }
    if (file.size > MAX_BYTES) {
      setClientError('That photo is over 8 MB. Choose a smaller one.')
      return
    }
    setClientError(null)
    upload.mutate(
      { file, kind },
      {
        onSuccess: () => {
          setPicking(false)
          if (input.current) input.current.value = ''
        },
      },
    )
  }

  const serverError = upload.error ? fieldErrors(upload.error).photo ?? upload.error.message : null

  return (
    <section className="rounded-card border border-border2 bg-surface p-4">
      <div className="mb-3 flex items-center">
        <h2 className="text-xs font-bold uppercase tracking-[0.1em] text-text3">Photos</h2>
        <span className="flex-1" />
        {!picking ? (
          <button
            type="button"
            onClick={pick}
            className="text-[12.5px] font-semibold text-roomNum hover:underline"
          >
            + Add photo
          </button>
        ) : null}
      </div>

      {picking ? (
        <div className="mb-3 flex items-center gap-2">
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value as 'before' | 'after')}
            disabled={upload.isPending}
            aria-label="Photo kind"
            className="h-9 rounded border border-border3 bg-surface2 px-2 text-xs text-text focus:border-accent focus:outline-none"
          >
            <option value="before">Before</option>
            <option value="after">After</option>
          </select>
          <input
            ref={input}
            type="file"
            accept={ACCEPTED.join(',')}
            aria-label="Photo file"
            disabled={upload.isPending}
            onChange={(event) => onFile(event.target.files?.[0])}
            className="text-xs text-text3"
          />
          {upload.isPending ? <span className="text-xs text-text3">Uploading…</span> : null}
          <button
            type="button"
            onClick={() => {
              setPicking(false)
              setClientError(null)
            }}
            className="ml-auto text-xs text-text3 hover:text-text"
          >
            Cancel
          </button>
        </div>
      ) : null}

      {clientError ?? serverError ? (
        <p role="alert" className="mb-3 rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
          {clientError ?? serverError}
        </p>
      ) : null}

      {photos.length === 0 ? (
        <p className="text-xs text-text3">None yet</p>
      ) : (
        <div className="flex flex-wrap gap-3">
          {photos.map((photo) => (
            <figure key={photo.id} className="w-[140px]">
              <img
                src={photo.url}
                alt={`${KIND_LABEL[photo.kind]} photo`}
                className="h-[100px] w-full rounded object-cover"
              />
              <figcaption className="mt-1 text-[11.5px] text-text3">
                {KIND_LABEL[photo.kind]} · {formatClock(photo.createdAt)}
                {photo.uploadedByName ? ` · ${photo.uploadedByName}` : ''}
              </figcaption>
            </figure>
          ))}
        </div>
      )}
    </section>
  )
}
