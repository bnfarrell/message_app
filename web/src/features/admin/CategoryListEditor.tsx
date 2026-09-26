import { Button, Input } from '../../components/ui'
import { FieldError, LABEL, type CategoryOption } from './ItemListEditor'

/** A category being edited: `key` is what items point at; `id` is set once it is saved. */
export type CategoryDraft = CategoryOption & { id?: string }

let lastKey = 0

/** A request-local key for a category that has no id yet (checklist structure spec §3.2). */
export function newCategoryKey(): string {
  lastKey += 1
  return `new-${lastKey}`
}

/** Add, rename, reorder and remove a checklist's categories (spec §4.1). */
export function CategoryListEditor({ categories, onChange, error }: {
  categories: CategoryDraft[]
  onChange: (categories: CategoryDraft[]) => void
  error?: string
}) {
  const rename = (index: number, name: string) =>
    onChange(categories.map((c, i) => (i === index ? { ...c, name } : c)))
  const move = (index: number, delta: number) => {
    const target = index + delta
    if (target < 0 || target >= categories.length) return
    const next = [...categories]
    const held = next[index]!
    next[index] = next[target]!
    next[target] = held
    onChange(next)
  }

  return (
    <div>
      <div className="mb-1 flex items-center">
        <p className={LABEL}>Categories</p>
        <Button className="ml-auto" onClick={() => onChange([...categories, { key: newCategoryKey(), name: '' }])}>
          Add category
        </Button>
      </div>
      <FieldError message={error} />
      {categories.length === 0 ? (
        <p className="text-xs text-text3">None — every item shows in one list.</p>
      ) : (
        <ol className="flex flex-col gap-2">
          {categories.map((category, index) => {
            const n = index + 1
            return (
              <li key={category.key} className="flex items-center gap-1">
                <Input aria-label={`Name for category ${n}`} value={category.name} maxLength={120}
                       placeholder="Category name" onChange={(e) => rename(index, e.target.value)} />
                <Button variant="ghost" aria-label={`Move category ${n} up`} onClick={() => move(index, -1)}>↑</Button>
                <Button variant="ghost" aria-label={`Move category ${n} down`} onClick={() => move(index, 1)}>↓</Button>
                <Button variant="ghost" className="text-dangerText" aria-label={`Remove category ${n}`}
                        onClick={() => onChange(categories.filter((_, i) => i !== index))}>
                  Remove
                </Button>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}
