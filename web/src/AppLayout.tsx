import { Outlet } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { ThemeProvider } from './theme/ThemeContext'

export function AppLayout() {
  return (
    <ThemeProvider>
      <AppShell>
        <Outlet />
      </AppShell>
    </ThemeProvider>
  )
}
