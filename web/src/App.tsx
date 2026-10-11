import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'
import { Nav } from './components/Nav.tsx'
import { SmoothScroll } from './components/SmoothScroll.tsx'
import TargetCursor from './components/TargetCursor.tsx'
import { DashboardPage } from './routes/DashboardPage.tsx'

const ProductPage = lazy(() => import('./routes/ProductPage.tsx').then((module) => ({ default: module.ProductPage })))

export function App() {
  return (
    <SmoothScroll>
      <TargetCursor
        spinDuration={2}
        hoverDuration={0.2}
        size={36}
        cornerSize={12}
        thickness={3}
        padding={6}
        dotSize={4}
        cursorColor="#ffffff"
        cursorColorOnTarget="#ffffff"
        blendMode="difference"
        parallaxOn
        matchRadius
        showLabel
        clickEffect
        hideDefaultCursor
      />
      <Nav />
      <Routes>
        <Route path="/" element={<Suspense fallback={<main className="page-inset pt-28">Loading…</main>}><ProductPage /></Suspense>} />
        <Route path="/dashboard" element={<DashboardPage />} />
      </Routes>
    </SmoothScroll>
  )
}
