import type { ComponentProps } from 'react'

/** Native choices keep keyboard navigation and mobile pickers, with a shared visual treatment. */
export function Select({ className = '', children, ...props }: ComponentProps<'select'>) {
  return (
    <span className="select-control">
      <select data-cursor-label="Choose" {...props} className={`cursor-target ${className}`}>
        {children}
      </select>
      <svg className="select-chevron" aria-hidden="true" focusable="false" viewBox="0 0 16 16" fill="none">
        <path d="m4 6 4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  )
}
