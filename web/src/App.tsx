import { BrowserRouter } from 'react-router-dom'
import { AppRoutes } from './routes'
import { ErrorBoundary } from './components/ErrorBoundary'
import { ToastProvider } from './components/ui'

export default function App() {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <AppRoutes />
        </BrowserRouter>
      </ToastProvider>
    </ErrorBoundary>
  )
}
