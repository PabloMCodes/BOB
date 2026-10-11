"""Debug SVG of one session's Twin data — a check view for the physical walk test, not the product UI.

Solid path = delivered in real time; dashed = backfilled (history synced later). Up = the direction the
phone faced at session start (not compass north). Pins = observed from here (camera position).
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from ..api.models import Pins, Track
from .projection import svg_heading

SIZE, PAD = 640, 48
COLORS = {"ppe": "#d62728", "restricted_zone": "#ff7f0e", "person_in_path": "#9467bd", "walkway": "#8c564b",
          "evidence": "#7f7f7f"}


def render(track: Track, pins: Pins, source_mode: str, link_state: str) -> str:
    xs = [p.pose.x_m for s in track.segments for p in s.points] + [p.pose.x_m for p in pins.pins]
    zs = [p.pose.z_m for s in track.segments for p in s.points] + [p.pose.z_m for p in pins.pins]
    if pins.marker.pose is not None:
        xs.append(pins.marker.pose.x_m)
        zs.append(pins.marker.pose.z_m)
    xs, zs = xs or [0.0], zs or [0.0]
    span = max(max(xs) - min(xs), max(zs) - min(zs), 1.0)
    scale = (SIZE - 2 * PAD) / span
    cx, cz = (max(xs) + min(xs)) / 2, (max(zs) + min(zs)) / 2

    def at(x: float, z: float) -> tuple[float, float]:
        return SIZE / 2 + (x - cx) * scale, SIZE / 2 + (z - cz) * scale

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE + 90}" '
             f'viewBox="0 0 {SIZE} {SIZE + 90}" font-family="sans-serif" font-size="11">',
             f'<rect width="{SIZE}" height="{SIZE + 90}" fill="#ffffff"/>']
    grid = int(span) + 2
    for i in range(-grid, grid + 1):  # 1 m grid around the centre
        x1, y1 = at(cx + i - (cx % 1), cz - grid)
        x2, y2 = at(cx + i - (cx % 1), cz + grid)
        parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#eeeeee"/>')
        x1, y1 = at(cx - grid, cz + i - (cz % 1))
        x2, y2 = at(cx + grid, cz + i - (cz % 1))
        parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#eeeeee"/>')
    for seg in track.segments:
        pts = " ".join(f"{a:.1f},{b:.1f}" for a, b in (at(p.pose.x_m, p.pose.z_m) for p in seg.points))
        dash = ' stroke-dasharray="6 4"' if seg.delivery != "realtime" else ""
        parts.append(f'<polyline class="segment-{escape(seg.delivery)}" points="{pts}" fill="none" stroke="#1f77b4" '
                     f'stroke-width="2"{dash}/>')
    ox, oy = at(0.0, 0.0)
    parts.append(f'<circle cx="{ox:.1f}" cy="{oy:.1f}" r="4" fill="none" stroke="#000"/>'
                 f'<text x="{ox + 6:.1f}" y="{oy - 6:.1f}">session origin</text>')
    for pin in pins.pins:
        px, py = at(pin.pose.x_m, pin.pose.z_m)
        color = COLORS.get(pin.hazard or "evidence", "#7f7f7f")
        shape = (f'<circle cx="{px:.1f}" cy="{py:.1f}" r="6" fill="{color}" fill-opacity="0.85"/>' if pin.kind == "incident"
                 else f'<rect x="{px - 4:.1f}" y="{py - 4:.1f}" width="8" height="8" fill="{color}"/>')
        title = f"{pin.label} ({pin.state or 'evidence'}, {pin.source_mode.value}, {pin.delivery.value}) — {pin.meaning}"
        parts.append(f'<g class="pin-{pin.kind}"><title>{escape(title)}</title>{shape}</g>')
    m = pins.marker
    if m.pose is not None:
        mx, my = at(m.pose.x_m, m.pose.z_m)
        hx, hy = svg_heading(m.pose.yaw_rad)
        tip, left, right = (mx + hx * 14, my + hy * 14), (mx - hy * 6, my + hx * 6), (mx + hy * 6, my - hx * 6)
        fill = {"current": "#2ca02c", "last_known": "#bcbd22", "unknown": "#c7c7c7"}[m.status]
        parts.append(f'<polygon class="marker-{m.status}" points="{tip[0]:.1f},{tip[1]:.1f} {left[0]:.1f},{left[1]:.1f} '
                     f'{right[0]:.1f},{right[1]:.1f}" fill="{fill}" stroke="#000"><title>{escape(m.label + ": " + m.note)}'
                     f'</title></polygon>')
    banner = f"{source_mode} · session {str(track.session_id)[:8]} · link {link_state}"
    lines = [banner, f"{m.label}: {m.status} — {m.note}",
             f"up = phone's initial facing (not compass north) · 1 m grid · {len(pins.pins)} pins, "
             f"{len(pins.unlocalized)} unlocalized · solid = realtime, dashed = backfilled",
             "pins = observed from here (camera position), not person or hazard positions · DEBUG VIEW"]
    for i, line in enumerate(lines):
        weight = ' font-weight="bold" font-size="14"' if i == 0 else ""
        color = ' fill="#d62728"' if i == 0 and source_mode == "SAMPLE" else ""
        parts.append(f'<text x="8" y="{SIZE + 18 + i * 18}"{weight}{color}>{escape(line)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)
