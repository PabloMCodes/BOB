import { useEffect, type ReactNode } from 'react'
import { ReactLenis } from 'lenis/react'
import { useLocation } from 'react-router-dom'
import { useReduced } from '../hooks/useMediaQuery.ts'

/** Lenis runs on the homepage only, so dashboard panels keep native nested scrolling. */
export function SmoothScroll({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  const reduced = useReduced()

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  return (
    <>
      {reduced || pathname !== '/' ? null : (
        <ReactLenis root options={{ lerp: 0.1, smoothWheel: true }} />
      )}
      {children}
    </>
  )
}
