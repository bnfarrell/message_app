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
  /** Checklists only: the `key` of the category this item sits under. PM never sets it. */
  categoryKey?: string | null
}

/** A category as the item editor needs it: the client-side key items point at, and a name. */
export type CategoryOption = { key: string; name: string }

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

/**
 * Items in the order the grouped editor shows them: ungrouped first, then each category's items
 * in category order; a stable sort, so items keep their relative order within a group. An item
 * naming a category that is not in `categories` counts as ungrouped.
 */
export function orderByCategory(items: ItemDraft[], categories: CategoryOption[]): ItemDraft[] {
  const rank = new Map(categories.map((c, i) => [c.key, i]))
  const groupOf = (item: ItemDraft) =>
    item.categoryKey != null && rank.has(item.categoryKey) ? rank.get(item.categoryKey)! : -1
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => groupOf(a.item) - groupOf(b.item) || a.index - b.index)
    .map(({ item }) => item)
}

export function FieldError({ message }: { message?: string }) {
  if (!message) return null
  return <p className="mt-1 text-xs text-dangerText">{message}</p>
}

/**
 * The typed item list shared by PM and checklist templates. `categories` is optional: PM never
 * passes it and gets exactly the flat list it always had. With it, each item gains a Category
 * select and the list renders grouped — ungrouped items first, then one heading per category —
 * and `onChange` always receives the items in that grouped order, so what is saved is what is
 * shown. Moving an item up or down stays inside its group; the select moves it between groups.
 */
export function ItemListEditor({ items, onChange, error, categories }: {
  items: ItemDraft[]
  onChange: (items: ItemDraft[]) => void
  error?: string
  categories?: CategoryOption[]
}) {
  const list = categories ? orderByCategory(items, categories) : items
  const known = new Set((categories ?? []).map((c) => c.key))
  const groupKey = (item: ItemDraft) =>
    item.categoryKey != null && known.has(item.categoryKey) ? item.categoryKey : null
  const editItem = (index: number, change: Partial<ItemDraft>) =>
    onChange(list.map((item, i) => (i === index ? { ...item, ...change } : item)))
  const moveItem = (index: number, delta: number) => {
    const target = index + delta
    if (target < 0 || target >= list.length) return
    if (categories && groupKey(list[index]!) !== groupKey(list[target]!)) return
    const next = [...list]
    const held = next[index]!
    next[index] = next[target]!
    next[target] = held
    onChange(next)
  }

  const renderItem = (item: ItemDraft, index: number) => {
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
          {categories ? (
            <select aria-label={`Category for item ${n}`} className={SELECT}
                    value={groupKey(item) ?? ''}
                    onChange={(e) => editItem(index, { categoryKey: e.target.value || null })}>
              <option value="">None</option>
              {categories.map((c) => (
                <option key={c.key} value={c.key}>{c.name.trim() || 'Untitled category'}</option>
              ))}
            </select>
          ) : null}
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
                    onClick={() => onChange(list.filter((_, i) => i !== index))}>
              Remove
            </Button>
          </div>
        </div>
      </li>
    )
  }

  const indexed = list.map((item, index) => ({ item, index }))
  return (
    <div>
      <div className="mb-1 flex items-center">
        <p className={LABEL}>Checklist</p>
        <Button className="ml-auto" onClick={() => onChange([...list, { ...NEW_ITEM }])}>
          Add item
        </Button>
      </div>
      <FieldError message={error} />
      {categories ? (
        <div className="flex flex-col gap-3">
          <ol className="flex flex-col gap-2">
            {indexed.filter(({ item }) => groupKey(item) === null)
              .map(({ item, index }) => renderItem(item, index))}
          </ol>
          {categories.map((category) => {
            const members = indexed.filter(({ item }) => groupKey(item) === category.key)
            return (
              <section key={category.key} aria-label={`Items in ${category.name.trim() || 'Untitled category'}`}>
                <h3 className="mb-1 text-xs font-bold text-text2">{category.name.trim() || 'Untitled category'}</h3>
                {members.length === 0 ? (
                  <p className="text-xs text-text3">No items yet — pick this category on an item.</p>
                ) : (
                  <ol className="flex flex-col gap-2">
                    {members.map(({ item, index }) => renderItem(item, index))}
                  </ol>
                )}
              </section>
            )
          })}
        </div>
      ) : (
        <ol className="flex flex-col gap-2">
          {list.map((item, index) => renderItem(item, index))}
        </ol>
      )}
    </div>
  )
}
