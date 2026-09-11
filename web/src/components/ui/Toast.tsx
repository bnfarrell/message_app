import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { cn } from '../../lib/cn'

type Toast = { id: number; message: string; tone: 'ok' | 'danger' }

const ToastContext = createContext<((message: string, tone?: 'ok' | 'danger') => void) | null>(null)

export function useToast() {
  const push = useContext(ToastContext)
  if (!push) throw new Error('useToast must be used inside a ToastProvider')
  return push
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const timers = useRef(new Set<ReturnType<typeof setTimeout>>())

  useEffect(() => {
    const pending = timers.current
    return () => {
      pending.forEach((timer) => clearTimeout(timer))
      pending.clear()
    }
  }, [])

  const push = useCallback((message: string, tone: 'ok' | 'danger' = 'ok') => {
    const id = Date.now() + Math.random()
    setToasts((current) => [...current, { id, message, tone }])
    const timer = setTimeout(() => {
      timers.current.delete(timer)
      setToasts((current) => current.filter((t) => t.id !== id))
    }, 5000)
    timers.current.add(timer)
  }, [])

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              'rounded border px-4 py-3 text-sm font-semibold',
              t.tone === 'ok'
                ? 'border-okBorder bg-okBg text-okText'
                : 'border-danger bg-dangerBg text-dangerText',
            )}
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
