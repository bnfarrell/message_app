import { Outlet } from 'react-router-dom'
import { RealtimeProvider } from './api/ws'
import { AppShell } from './components/AppShell'
import { ThemeProvider } from './theme/ThemeContext'

export function AppLayout() {
  return (
    <ThemeProvider>
      <RealtimeProvider>
        <AppShell>
          <Outlet />
        </AppShell>
      </RealtimeProvider>
    </ThemeProvider>
  )
}
