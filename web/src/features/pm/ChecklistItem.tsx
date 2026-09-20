import { useEffect, useState, type ReactNode } from 'react'
import type { AnswerPatch, RunAnswerOut, RunPhotoOut, TemplateItemOut } from '../../api/types'
import { Input } from '../../components/ui'
import { cn } from '../../lib/cn'

const LABEL = 'text-sm font-semibold'
const HINT = 'text-xs text-text3'

/** One checklist row, rendered by `item.itemType`. Every change is saved as its own PATCH
 *  through `onSave`; nothing is queued locally, so leaving the page mid-room loses nothing. */
export function ChecklistItem({
  item,
  answer,
  photos,
  readOnly,
  missing,
  onSave,
  onUpload,
}: {
  item: TemplateItemOut
  answer?: RunAnswerOut
  photos: RunPhotoOut[]
  readOnly: boolean
  missing: boolean
  onSave: (patch: AnswerPatch) => void
  onUpload: (file: File) => void
}) {
  const inputId = `pm-item-${item.id}`
  const required = item.required ? <span className="text-dangerText"> *</span> : null

  // Text and number are edited locally and saved on blur, so a slow connection does not
  // fight the keyboard. The saved value wins whenever the server answers.
  const [text, setText] = useState(answer?.textValue ?? '')
  const [number, setNumber] = useState(answer?.numberValue === null || answer?.numberValue === undefined ? '' : String(answer.numberValue))
  useEffect(() => setText(answer?.textValue ?? ''), [answer?.textValue])
  useEffect(() => {
    setNumber(answer?.numberValue === null || answer?.numberValue === undefined ? '' : String(answer.numberValue))
  }, [answer?.numberValue])

  const bounds =
    item.minValue !== null && item.minValue !== undefined && item.maxValue !== null && item.maxValue !== undefined
      ? `${item.minValue}–${item.maxValue}`
      : item.minValue !== null && item.minValue !== undefined
        ? `≥ ${item.minValue}`
        : item.maxValue !== null && item.maxValue !== undefined
          ? `≤ ${item.maxValue}`
          : null

  let control: ReactNode
  switch (item.itemType) {
    case 'checkbox':
      control = (
        <label className="flex items-center gap-3">
          <input
            id={inputId}
            type="checkbox"
            className="h-5 w-5"
            checked={answer?.boolValue === true}
            disabled={readOnly}
            onChange={(event) => onSave({ boolValue: event.target.checked })}
          />
          <span className={LABEL}>{item.label}{required}</span>
        </label>
      )
      break
    case 'number':
      control = (
        <div>
          <label className={LABEL} htmlFor={inputId}>{item.label}{required}</label>
          <div className="mt-1 flex items-center gap-2">
            <Input
              id={inputId}
              type="number"
              inputMode="decimal"
              step="any"
              className={cn('max-w-[160px]', answer?.outOfRange && 'border-danger text-dangerText')}
              value={number}
              disabled={readOnly}
              onChange={(event) => setNumber(event.target.value)}
              onBlur={() => onSave({ numberValue: number === '' ? null : Number(number) })}
            />
            {item.unit ? <span className="text-sm text-text3">{item.unit}</span> : null}
          </div>
          {bounds ? <p className={HINT}>Expected {bounds}{item.unit ? ` ${item.unit}` : ''}</p> : null}
          {answer?.outOfRange ? (
            <p role="alert" className="mt-1 text-xs font-semibold text-dangerText">
              Outside {bounds} — a work order will be raised when this PM is completed.
            </p>
          ) : null}
        </div>
      )
      break
    case 'text':
      control = (
        <div>
          <label className={LABEL} htmlFor={inputId}>{item.label}{required}</label>
          <Input
            id={inputId}
            className="mt-1"
            value={text}
            disabled={readOnly}
            maxLength={2000}
            onChange={(event) => setText(event.target.value)}
            onBlur={() => {
              if ((answer?.textValue ?? '') !== text) onSave({ textValue: text || null })
            }}
          />
        </div>
      )
      break
    case 'photo':
      control = (
        <div>
          <label className={LABEL} htmlFor={inputId}>{item.label}{required}</label>
          {photos.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-2">
              {photos.map((photo) => (
                <a key={photo.id} href={photo.url} target="_blank" rel="noreferrer">
                  <img src={photo.url} alt="" className="h-20 w-20 rounded object-cover" />
                </a>
              ))}
            </div>
          ) : null}
          {readOnly ? null : (
            <input
              id={inputId}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              capture="environment"
              className="mt-2 block text-sm"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) onUpload(file)
                event.target.value = ''
              }}
            />
          )}
        </div>
      )
      break
  }

  return (
    <li className={cn('rounded-card border bg-surface p-4', missing ? 'border-warnText/40' : 'border-border2')}>
      {control}
    </li>
  )
}
