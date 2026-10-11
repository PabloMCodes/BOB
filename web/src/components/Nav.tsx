import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useMotionValueEvent, useScroll } from 'motion/react'
import { copy } from '../data/copy.ts'

function linkClass({ isActive }: { isActive: boolean }) {
  return `cursor-target label-type transition-colors duration-300 ${isActive ? 'text-ink' : 'text-muted hover:text-ink'}`
}

export function Nav() {
  const { scrollY } = useScroll()
  const [scrolled, setScrolled] = useState(false)
  useMotionValueEvent(scrollY, 'change', (y) => setScrolled(y > 10))

  return (
    <header
      className={`fixed inset-x-0 top-0 z-30 h-16 border-b transition-[background-color,border-color,backdrop-filter] duration-300 ${
        scrolled ? 'border-line bg-canvas/90 backdrop-blur-md' : 'border-transparent bg-transparent'
      }`}
    >
      <div className="page-inset flex h-full items-center justify-between gap-3 sm:gap-6">
        <NavLink to="/" end className="cursor-target text-[1.05rem] font-semibold tracking-[-0.02em] text-ink" data-cursor-label="Home">
          {copy.wordmark}
        </NavLink>
        <nav aria-label="Main navigation" className="flex items-center gap-3 sm:gap-6 [&_.label-type]:text-[0.65rem] sm:[&_.label-type]:text-[0.8125rem]">
          <NavLink to="/" end className={linkClass} data-cursor-label="Product">
            {copy.nav.product}
          </NavLink>
          <NavLink to="/dashboard" className={linkClass} data-cursor-label="Dashboard">
            {copy.nav.dashboard}
          </NavLink>
          <NavLink to="/inspiration" className={linkClass} data-cursor-label="Inspiration">
            {copy.nav.inspiration}
          </NavLink>
          {copy.links.github ? (
            <a
              href={copy.links.github}
              className="cursor-target label-type hidden text-muted transition-colors duration-300 hover:text-ink sm:block"
              data-cursor-label="GitHub"
              target="_blank"
              rel="noreferrer"
            >
              {copy.nav.github}
            </a>
          ) : null}
        </nav>
      </div>
    </header>
  )
}
