import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { useLogout, useSessionQuery } from '../api/hooks/auth'
import type { MembershipOut, Role, UserOut } from '../api/types'
import { hasCapability, type Capability } from './capabilities'
import { ACTIVE_PROPERTY_KEY } from './storage'

export type Session = {
  user: UserOut
  memberships: MembershipOut[]
  membership: MembershipOut
  propertyId: string
  role: Role
  can: (capability: Capability) => boolean
  setPropertyId: (id: string) => void
  logout: () => void
}

const SessionContext = createContext<Session | null>(null)

export function useSession(): Session {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession must be used inside a SessionProvider')
  return value
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const { data } = useSessionQuery()
  // `mutate` is a stable reference in TanStack Query v5; the mutation object itself is not,
  // so depending on that would defeat the memo below and re-render every consumer constantly.
  const { mutate: logout } = useLogout()
  const [stored, setStored] = useState<string | null>(() => {
    try {
      return localStorage.getItem(ACTIVE_PROPERTY_KEY)
    } catch {
      return null // private mode / blocked storage: fall back to the first membership
    }
  })

  const setPropertyId = useCallback((id: string) => {
    setStored(id)
    try {
      localStorage.setItem(ACTIVE_PROPERTY_KEY, id)
    } catch {
      /* not fatal — the choice just will not survive a reload */
    }
  }, [])

  const value = useMemo<Session | null>(() => {
    if (!data || data.memberships.length === 0) return null
    const membership =
      data.memberships.find((m) => m.propertyId === stored) ?? data.memberships[0]!
    return {
      user: data.user,
      memberships: data.memberships,
      membership,
      propertyId: membership.propertyId,
      role: membership.role,
      can: (capability) => hasCapability(membership.role, capability),
      setPropertyId,
      logout: () => logout(),
    }
  }, [data, stored, setPropertyId, logout])

  if (!value) return null
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}
