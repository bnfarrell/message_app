import { useEffect, useState } from 'react'

// Absent in older jsdom and some embedded webviews — false (desktop-shaped) is the safe
// default there, matching how ThemeContext's devicePrefersDark falls back for the same reason.
function evaluate(query: string): boolean {
  return window.matchMedia?.(query).matches ?? false
}

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => evaluate(query))

  useEffect(() => {
    const mql = window.matchMedia?.(query)
    if (!mql) return
    const onChange = () => setMatches(mql.matches)
    onChange()
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [query])

  return matches
}
