import { useEffect, useState } from 'react'
import { errorMessage } from './api.ts'

/** One request in flight, bounded timeout, and an independent stale deadline. */
export function usePoll<T>(load: (signal: AbortSignal) => Promise<T>, interval = 1500, revision = 0) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [stale, setStale] = useState(true)
  const [updated, setUpdated] = useState<Date | null>(null)
  useEffect(() => {
    let stopped = false
    let timer: ReturnType<typeof setTimeout>
    let staleTimer: ReturnType<typeof setTimeout>
    let controller: AbortController
    async function refresh() {
      controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 6000)
      try {
        const value = await load(controller.signal)
        if (!stopped) {
          setData(value); setError(''); setStale(false); setUpdated(new Date())
          clearTimeout(staleTimer)
          staleTimer = setTimeout(() => setStale(true), 3000)
        }
      } catch (cause) {
        if (!stopped) { setError(errorMessage(cause)); setStale(true) }
      } finally {
        clearTimeout(timeout)
        controller.abort()
        if (!stopped) timer = setTimeout(refresh, document.hidden ? Math.max(interval, 5000) : interval)
      }
    }
    void refresh()
    return () => { stopped = true; clearTimeout(timer); clearTimeout(staleTimer); controller?.abort() }
  }, [load, interval, revision])
  return { data, error, stale, updated }
}
