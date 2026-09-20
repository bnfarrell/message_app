import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useSession } from './auth/SessionContext'
import { RequireAuth } from './auth/RequireAuth'
import { type Capability, landingPath } from './auth/capabilities'
import { AppLayout } from './AppLayout'
import { Spinner } from './components/ui'
import { LoginPage } from './features/login/LoginPage'
import { InboxPage } from './features/inbox/InboxPage'
import { BoardPage } from './features/board/BoardPage'
import { WorkOrderDetailPage } from './features/board/WorkOrderDetailPage'
import { AnalyticsPage } from './features/analytics/AnalyticsPage'
import { NotificationsPage } from './features/notifications/NotificationsPage'
import { MessagesPage } from './features/messages/MessagesPage'
import { LogPage } from './features/log/LogPage'
import { AdminPage } from './features/admin/AdminPage'
import { SweepPage } from './features/pm/SweepPage'
import { RunPage } from './features/pm/RunPage'
import { InspectionPage } from './features/pm/InspectionPage'

function LandingRedirect() {
  const { role } = useSession()
  return <Navigate to={landingPath(role)} replace />
}

function RequireCapability({
  capability,
  children,
}: {
  capability: Capability
  children: JSX.Element
}) {
  const { can, role } = useSession()
  if (!can(capability)) return <Navigate to={landingPath(role)} replace />
  return children
}

// Statically false in a production build, so Rollup drops the import entirely.
const SimulatorPage = import.meta.env.DEV
  ? lazy(() => import('./features/sim/SimulatorPage'))
  : null

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/app" element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route index element={<LandingRedirect />} />
          <Route path="inbox" element={<InboxPage />} />
          <Route path="inbox/:id" element={<InboxPage />} />
          <Route path="board" element={<BoardPage />} />
          <Route path="work-orders/:id" element={<WorkOrderDetailPage />} />
          <Route
            path="analytics"
            element={
              <RequireCapability capability="view_property_analytics">
                <AnalyticsPage />
              </RequireCapability>
            }
          />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="messages" element={<MessagesPage />} />
          <Route path="messages/:id" element={<MessagesPage />} />
          <Route path="log" element={<LogPage />} />
          <Route path="pm" element={<SweepPage />} />
          <Route path="pm/runs/:id" element={<RunPage />} />
          <Route
            path="inspection"
            element={
              <RequireCapability capability="inspect_pm">
                <InspectionPage />
              </RequireCapability>
            }
          />
          <Route
            path="admin/*"
            element={
              <RequireCapability capability="manage_admin">
                <AdminPage />
              </RequireCapability>
            }
          />
        </Route>
      </Route>
      {SimulatorPage ? (
        <Route
          path="/sim"
          element={
            <Suspense fallback={<Spinner />}>
              <SimulatorPage />
            </Suspense>
          }
        />
      ) : null}
      <Route path="*" element={<Navigate to="/app" replace />} />
    </Routes>
  )
}
