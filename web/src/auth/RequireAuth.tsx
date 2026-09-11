import { useEffect, useRef } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useSessionQuery } from '../api/hooks/auth'
import { onUnauthorized } from '../api/client'
import { Spinner } from '../components/ui'
import { SessionProvider } from './SessionContext'
import { clearActivePropertyId } from './storage'

export function RequireAuth() {
  const { data, isPending, error, refetch } = useSessionQuery()
  const location = useLocation()
  // A truly-dead session makes refetch()'s own /api/auth/me call 401 too, which would
  // re-invoke this same handler and refetch again forever. Guard against that: ignore an
  // unauthorized signal that arrives while a refetch it triggered is still in flight.
  const refetching = useRef(false)

  // Any 401 from any request means the cookie died mid-session; refetching /api/auth/me
  // flips this guard to the redirect below instead of leaving a half-dead screen up.
  useEffect(() => {
    onUnauthorized(() => {
      if (refetching.current) return
      refetching.current = true
      void refetch().finally(() => {
        refetching.current = false
      })
    })
    return () => onUnauthorized(null)
  }, [refetch])

  // A session can end without anyone signing out — cookie expiry, a server restart, a TTL — and
  // that path never invokes `useLogout`, so its localStorage cleanup never runs. Left alone, the
  // stored active property outlives the session on a shared front-desk machine: the original
  // cross-user bleed by a different door (ruling D56).
  //
  // `isPending` is part of the condition, not decoration: on a cold start `data` is undefined
  // while the first /api/auth/me is in flight, so without it every normal load would clear the
  // very preference it is about to use.
  const sessionLost = !isPending && (Boolean(error) || !data)
  useEffect(() => {
    if (sessionLost) clearActivePropertyId()
  }, [sessionLost])

  if (isPending) {
    return (
      <div className="grid h-full place-items-center bg-bg">
        <Spinner />
      </div>
    )
  }

  if (error || !data) {
    const from = `${location.pathname}${location.search}`
    return <Navigate to="/login" replace state={{ from }} />
  }

  if (data.memberships.length === 0) {
    return (
      <div className="grid h-full place-items-center bg-bg p-8 text-center">
        <p className="max-w-sm text-text2">
          Your account has no property access yet. Ask an administrator to add you to a property.
        </p>
      </div>
    )
  }

  return (
    <SessionProvider>
      <Outlet />
    </SessionProvider>
  )
}
