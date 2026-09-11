import { Outlet } from 'react-router-dom'
import { useUnreadCount } from './api/hooks/notifications'
import { RealtimeProvider } from './api/ws'
import { AppShell } from './components/AppShell'
import { ThemeProvider } from './theme/ThemeContext'

function Shell() {
  // The shell stays fetch-free (Task 9); the count is fed in from here.
  const unread = useUnreadCount()
  return (
    <AppShell unreadCount={unread.data?.count}>
      <Outlet />
    </AppShell>
  )
}

export function AppLayout() {
  return (
    <ThemeProvider>
      <RealtimeProvider>
        <Shell />
      </RealtimeProvider>
    </ThemeProvider>
  )
}
