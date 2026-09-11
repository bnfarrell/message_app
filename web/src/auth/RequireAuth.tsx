import { useEffect, useRef } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useSessionQuery } from '../api/hooks/auth'
import { onUnauthorized } from '../api/client'
import { Spinner } from '../components/ui'
import { SessionProvider } from './SessionContext'

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
