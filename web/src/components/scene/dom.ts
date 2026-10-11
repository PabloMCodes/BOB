/** Per-frame writes to overlay elements; the scene never re-renders React for these. */
export function setStyle(node: HTMLElement | SVGElement | null | undefined, values: Record<string, string>) {
  if (!node) return
  for (const [key, value] of Object.entries(values)) node.style.setProperty(key, value)
}

export function setAttributes(node: SVGElement | null | undefined, values: Record<string, string | number>) {
  if (!node) return
  for (const [key, value] of Object.entries(values)) node.setAttribute(key, String(value))
}
