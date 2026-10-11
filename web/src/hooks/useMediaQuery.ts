import { useSyncExternalStore } from 'react'

export const WIDE_QUERY = '(min-width: 1024px)'

export function useMediaQuery(query: string) {
  return useSyncExternalStore(
    (notify) => {
      const list = window.matchMedia(query)
      list.addEventListener('change', notify)
      return () => list.removeEventListener('change', notify)
    },
    () => window.matchMedia(query).matches,
  )
}

/** Pinned, scroll-driven layouts run only on wide screens with motion allowed. */
export function usePinned() {
  const wide = useMediaQuery(WIDE_QUERY)
  const reduced = useMediaQuery('(prefers-reduced-motion: reduce)')
  return wide && !reduced
}

export function useReduced() {
  return useMediaQuery('(prefers-reduced-motion: reduce)')
}
