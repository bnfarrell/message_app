import type { ChecklistCategoryProgressOut } from '../../api/types'

export type CategoryGroup<T> = ChecklistCategoryProgressOut & { items: T[] }

/**
 * A checklist's items as the checklist page shows them (checklist structure spec §2.2): the
 * ungrouped ones first, with no heading, then one group per category in the server's category
 * order. An item naming a category the server did not list counts as ungrouped, so nothing is
 * ever dropped from the page. Item order inside each part is the server's.
 */
export function groupByCategory<T extends { categoryId?: string | null }>(
  items: T[],
  categories: ChecklistCategoryProgressOut[],
): { ungrouped: T[]; groups: CategoryGroup<T>[] } {
  const known = new Set(categories.map((c) => c.id))
  return {
    ungrouped: items.filter((i) => !i.categoryId || !known.has(i.categoryId)),
    groups: categories.map((c) => ({ ...c, items: items.filter((i) => i.categoryId === c.id) })),
  }
}
