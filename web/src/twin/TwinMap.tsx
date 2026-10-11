import { useId } from 'react'
import type { Pins, Track } from './api.ts'

export function TwinMap({ track, pins, stale }: { track: Track; pins: Pins; stale: boolean }) {
  const gridId = useId()
  const marker = pins.marker
  const points = track.segments.flatMap((segment) => segment.points)
  const coordinates = [...points, ...pins.pins].map((point) => [point.east_m, point.north_m])
  if (marker.pose) coordinates.push([marker.pose.x_m, -marker.pose.z_m])
  coordinates.push([0, 0])
  let minX = 0, maxX = 0, minY = 0, maxY = 0
  for (const [x, y] of coordinates) {
    minX = Math.min(minX, x); maxX = Math.max(maxX, x)
    minY = Math.min(minY, y); maxY = Math.max(maxY, y)
  }
  const scale = Math.min(680 / Math.max(4, maxX - minX), 380 / Math.max(4, maxY - minY))
  const x = (east: number) => 400 + (east - (minX + maxX) / 2) * scale
  const y = (north: number) => 240 - (north - (minY + maxY) / 2) * scale
  const gridMetres = 10 ** Math.floor(Math.log10(80 / scale))
  const step = gridMetres * scale
  const isCurrent = !stale && marker.status === 'current'

  return (
    <svg viewBox="0 0 800 480" role="img" aria-label={`Session-local camera path with ${pins.pins.length} observation pins. ${stale ? 'Data is stale.' : marker.note}`} className="twin-map">
      <defs><pattern id={gridId} width={step} height={step} x={x(0)} y={y(0)} patternUnits="userSpaceOnUse">
        <path d={`M ${step} 0 H 0 V ${step}`} fill="none" stroke="var(--color-line)" strokeWidth="0.6" />
      </pattern></defs>
      <rect width="800" height="480" fill={`url(#${gridId})`} />
      <path d={`M ${x(0) - 7} ${y(0)} h 14 M ${x(0)} ${y(0) - 7} v 14`} stroke="var(--color-muted)" />
      <text x={x(0) + 10} y={y(0) + 18} className="twin-map-label">Origin</text>
      {track.segments.map((segment) => <g key={segment.segment}>
        {segment.points.map((point, i) => {
          const previous = segment.points[i - 1]
          const historical = point.delivery === 'backfilled' || previous?.delivery === 'backfilled'
          return previous ? <line key={point.seq_id} x1={x(previous.east_m)} y1={y(previous.north_m)} x2={x(point.east_m)} y2={y(point.north_m)}
            stroke="var(--color-ink)" strokeWidth="2" opacity={historical ? 0.45 : 0.85} strokeDasharray={historical ? '6 5' : undefined} /> :
            <circle key={point.seq_id} cx={x(point.east_m)} cy={y(point.north_m)} r="2" fill="var(--color-muted)" />
        })}
      </g>)}
      {pins.pins.map((pin, i) => <g key={`${pin.kind}:${pin.id}`}>
        <circle cx={x(pin.east_m)} cy={y(pin.north_m)} r="10" fill="var(--color-canvas)" stroke="var(--color-tape)" strokeWidth="1.5" strokeDasharray={pin.delivery === 'backfilled' ? '3 2' : undefined} />
        <text x={x(pin.east_m)} y={y(pin.north_m) + 3.5} textAnchor="middle" className="twin-pin-number">{i + 1}</text>
        <title>{`${pin.label} · ${pin.source_mode} · ${pin.delivery} · observed from here`}</title>
      </g>)}
      {marker.pose && <g transform={`translate(${x(marker.pose.x_m)} ${y(-marker.pose.z_m)})`}>
        <circle r="19" fill="var(--color-canvas)" stroke="var(--color-ink)" strokeDasharray={isCurrent ? undefined : '4 4'} opacity={isCurrent ? 1 : 0.6} />
        <path d="M 0 -13 L 8 9 L 0 5 L -8 9 Z" transform={`rotate(${-marker.pose.yaw_rad * 180 / Math.PI})`} fill={isCurrent ? 'var(--color-ink)' : 'var(--color-muted)'} />
        <title>{isCurrent ? 'Current phone camera' : 'Last known phone camera; current position unknown'}</title>
      </g>}
      <g transform="translate(32 32)">
        <path d="M 0 22 V 0 m -4 5 l 4 -5 l 4 5" fill="none" stroke="var(--color-muted)" />
        <text x="14" y="8" className="twin-map-label">Initial facing</text>
      </g>
      <g transform="translate(32 446)">
        <path d={`M 0 -4 V 0 H ${step} V -4`} fill="none" stroke="var(--color-muted)" />
        <text x={step + 10} y="4" className="twin-map-label">{gridMetres} m</text>
      </g>
    </svg>
  )
}
