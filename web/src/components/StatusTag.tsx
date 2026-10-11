import { statusLabel, type Status } from '../data/copy.ts'

type Tone = 'dark' | 'light' | 'chip'

const colors: Record<Tone, Record<Status, string>> = {
  dark: { built: 'text-ink', dev: 'text-tape' },
  light: { built: 'text-band-ink', dev: 'text-tape-deep' },
  chip: {
    built: 'rounded-full border-transparent bg-card/90 text-band-ink backdrop-blur-sm',
    dev: 'rounded-full border-transparent bg-card/90 text-tape-deep backdrop-blur-sm',
  },
}

export function StatusTag({ status, tone }: { status: Status; tone: Tone }) {
  return <span className={`status-tag ${colors[tone][status]}`}>{statusLabel[status]}</span>
}
