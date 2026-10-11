import type { ReactNode } from 'react'
import { motion } from 'motion/react'
import { useReduced } from '../hooks/useMediaQuery.ts'
import { EASE } from './motion.ts'

type RevealProps = {
  delay?: number
  className?: string
  children: ReactNode
}

export function Reveal({ delay = 0, className = '', children }: RevealProps) {
  const reduced = useReduced()
  if (reduced) return <div className={className}>{children}</div>
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{ duration: 0.7, ease: EASE, delay: Math.min(delay, 400) / 1000 }}
    >
      {children}
    </motion.div>
  )
}
