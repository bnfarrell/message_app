import { useState } from 'react'
import { useCategories } from '../../api/hooks/content'
import { usePatchConversation } from '../../api/hooks/conversations'
import type { CategoryOut } from '../../api/types'
import { Button, Dialog } from '../../components/ui'

/** Two levels is all the seed has; a tree widget here would be unearned. */
function flatten(categories: CategoryOut[], depth = 0): { id: string; label: string }[] {
  return categories.flatMap((category) => [
    { id: category.id, label: `${'  '.repeat(depth)}${category.name}` },
    ...flatten(category.children ?? [], depth + 1),
  ])
}

export function ArchiveDialog({
  conversationId,
  open,
  onClose,
}: {
  conversationId: string
  open: boolean
  onClose: () => void
}) {
  const { data: categories } = useCategories()
  const patch = usePatchConversation(conversationId)
  const [categoryId, setCategoryId] = useState('')
  const options = flatten((categories ?? []).filter((c) => c.active))

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Archive conversation"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            loading={patch.isPending}
            onClick={() =>
              patch.mutate(
                { status: 'archived', resolutionCategoryId: categoryId || null },
                { onSuccess: onClose },
              )
            }
          >
            Archive
          </Button>
        </>
      }
    >
      {patch.error ? (
        <p role="alert" className="rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
          {patch.error.message}
        </p>
      ) : null}
      <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-text3" htmlFor="archive-cat">
        Resolution category
      </label>
      <select
        id="archive-cat"
        className="h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none"
        value={categoryId}
        onChange={(event) => setCategoryId(event.target.value)}
      >
        <option value="">—</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>{option.label}</option>
        ))}
      </select>
      <p className="text-xs text-text3">Optional. Leave blank if none fits.</p>
    </Dialog>
  )
}
