import { requirements, type Item, type Observation } from './api.ts'
import type { Workspace } from '../twin/api.ts'

type ExportSnapshot = {
  workspace: Workspace
  stale: boolean
  refreshedAt: Date | null
  exportedAt: Date
}

// Always quote cells; keep user-supplied names/reasons from becoming formulas.
function cell(value: string | number | boolean | null | undefined): string {
  const text = String(value ?? '')
  const safe = typeof value === 'string' && (/^[\s\u0000-\u001f]*[=+\-@]/u.test(text) || /^[\t\r\n]/u.test(text)) ? `'${text}` : text
  return `"${safe.replaceAll('"', '""')}"`
}

/** One row per box, or one empty-box row when a frame has no detections.
 * Frame assessments are repeated without attributing them to a particular box.
 * Only explicitly selected metadata is exported, never image/evidence fields.
 */
export function detectionCsv(items: Item<Observation>[], snapshot: ExportSnapshot): string {
  const headers = [
    'workspace', 'exported_at_utc', 'last_refreshed_at_utc', 'snapshot_stale',
    'hub_received_at_utc', 'source_mode', 'delivery', 'session_id', 'event_id', 'frame_seq',
    'worksite_id', 'inspection_id', 'profile_revision', 'assessment_recorded', 'no_requirements_selected',
    'model_id', 'inference_ms', 'frame_detection_count', 'detection_index', 'detection_class',
    'detection_source', 'confidence_pct', 'confidence_basis',
    ...requirements.flatMap((name) => [`frame_${name}_status`, `frame_${name}_reason`]),
  ]
  const rows = [headers.map(cell).join(',')]
  // Match the displayed history's newest-first order; never mutate the poll data.
  for (const item of [...items].reverse()) {
    const { event, assessment } = item.record.body
    const common = [
      snapshot.workspace, snapshot.exportedAt.toISOString(), snapshot.refreshedAt?.toISOString(), snapshot.stale,
      new Date(item.hub_rx_wall_ns / 1e6).toISOString(), item.record.source_mode, item.delivery,
      event.session_id, event.event_id, event.seq_id,
      assessment?.worksite_id, assessment?.inspection_id, assessment?.profile_revision,
      assessment != null, assessment?.no_requirements_selected,
      event.model_id, event.inference_latency_ms, event.boxes.length,
    ]
    const statuses = requirements.flatMap((name) => {
      const check = assessment?.requirements.find((value) => value.requirement === name)
      return [check?.status, check?.reason]
    })
    const boxes = event.boxes.length ? event.boxes : [null]
    boxes.forEach((box, index) => {
      rows.push([
        ...common, box ? index + 1 : null, box?.cls_name, box?.source,
        box ? (box.conf * 100).toFixed(1) : null,
        box ? box.source === 'derived' ? 'subject' : 'detection' : null,
        ...statuses,
      ].map(cell).join(','))
    })
  }
  // UTF-8 BOM preserves labels in spreadsheet apps; CRLF is standard CSV framing.
  return `\uFEFF${rows.join('\r\n')}\r\n`
}
