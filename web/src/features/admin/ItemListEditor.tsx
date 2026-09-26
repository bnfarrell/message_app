import type { PmItemType, TemplateItemIn, TemplateItemOut } from '../../api/types'
import { Button, Input } from '../../components/ui'
import { ITEM_TYPE_LABELS } from '../pm/labels'

export type ItemDraft = {
  id?: string
  label: string
  itemType: PmItemType
  unit: string
  minValue: string
  maxValue: string
  required: boolean
}

export const NEW_ITEM: ItemDraft = { label: '', itemType: 'checkbox', unit: '', minValue: '', maxValue: '', required: true }

export const LABEL = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
export const SELECT = 'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

export function toItemIn(item: ItemDraft): TemplateItemIn {
  const number = item.itemType === 'number'
  return {
    ...(item.id ? { id: item.id } : {}),
    label: item.label.trim(),
    itemType: item.itemType,
    unit: number && item.unit.trim() ? item.unit.trim() : null,
    minValue: number && item.minValue.trim() !== '' ? Number(item.minValue) : null,
    maxValue: number && item.maxValue.trim() !== '' ? Number(item.maxValue) : null,
    required: item.required,
  }
}

export function itemDraftFrom(i: TemplateItemOut): ItemDraft {
  return {
    id: i.id, label: i.label, itemType: i.itemType, unit: i.unit ?? '',
    minValue: i.minValue === null || i.minValue === undefined ? '' : String(i.minValue),
    maxValue: i.maxValue === null || i.maxValue === undefined ? '' : String(i.maxValue),
    required: i.required,
  }
}

export function FieldError({ message }: { message?: string }) {
  if (!message) return null
  return <p className="mt-1 text-xs text-dangerText">{message}</p>
}

export function ItemListEditor({ items, onChange, error }: {
  items: ItemDraft[]
  onChange: (items: ItemDraft[]) => void
  error?: string
}) {
  const editItem = (index: number, change: Partial<ItemDraft>) =>
    onChange(items.map((item, i) => (i === index ? { ...item, ...change } : item)))
  const moveItem = (index: number, delta: number) => {
    const target = index + delta
    if (target < 0 || target >= items.length) return
    const next = [...items]
    const held = next[index]!
    next[index] = next[target]!
    next[target] = held
    onChange(next)
  }

  return (
    <div>
      <div className="mb-1 flex items-center">
        <p className={LABEL}>Checklist</p>
        <Button className="ml-auto" onClick={() => onChange([...items, { ...NEW_ITEM }])}>
          Add item
        </Button>
      </div>
      <FieldError message={error} />
      <ol className="flex flex-col gap-2">
        {items.map((item, index) => {
          const n = index + 1
          return (
            <li key={item.id ?? `new-${index}`} className="rounded border border-border2 p-2">
              <div className="flex flex-col gap-2">
                <Input aria-label={`Label for item ${n}`} value={item.label} maxLength={200}
                       placeholder="Label" onChange={(e) => editItem(index, { label: e.target.value })} />
                <div className="flex gap-2">
                  <select aria-label={`Type for item ${n}`} className={SELECT} value={item.itemType}
                          disabled={Boolean(item.id)}
                          onChange={(e) => editItem(index, { itemType: e.target.value as PmItemType })}>
                    {(Object.keys(ITEM_TYPE_LABELS) as PmItemType[]).map((t) => (
                      <option key={t} value={t}>{ITEM_TYPE_LABELS[t]}</option>
                    ))}
                  </select>
                  <label className="flex items-center gap-1 text-xs">
                    <input type="checkbox" checked={item.required}
                           onChange={(e) => editItem(index, { required: e.target.checked })} />
                    Required
                  </label>
                </div>
                {item.itemType === 'number' ? (
                  <div className="flex gap-2">
                    <Input aria-label={`Unit for item ${n}`} placeholder="Unit" className="w-20" maxLength={16}
                           value={item.unit} onChange={(e) => editItem(index, { unit: e.target.value })} />
                    <Input aria-label={`Min for item ${n}`} type="number" placeholder="Min" step="any"
                           value={item.minValue} onChange={(e) => editItem(index, { minValue: e.target.value })} />
                    <Input aria-label={`Max for item ${n}`} type="number" placeholder="Max" step="any"
                           value={item.maxValue} onChange={(e) => editItem(index, { maxValue: e.target.value })} />
                  </div>
                ) : null}
                <div className="flex gap-1">
                  <Button variant="ghost" aria-label={`Move item ${n} up`} onClick={() => moveItem(index, -1)}>↑</Button>
                  <Button variant="ghost" aria-label={`Move item ${n} down`} onClick={() => moveItem(index, 1)}>↓</Button>
                  <Button variant="ghost" className="ml-auto text-dangerText" aria-label={`Remove item ${n}`}
                          onClick={() => onChange(items.filter((_, i) => i !== index))}>
                    Remove
                  </Button>
                </div>
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
