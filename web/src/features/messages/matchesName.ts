/** Case- and accent-insensitive: "José" and "jose" are the same person to whoever is typing. */
function fold(text: string): string {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
}

/** The staff-messaging name filter (spec §6): a blank query matches everything. */
export function matchesName(name: string, query: string): boolean {
  const needle = fold(query.trim())
  return needle === '' || fold(name).includes(needle)
}
