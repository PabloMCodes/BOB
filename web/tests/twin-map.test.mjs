import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

const vite = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' })
after(() => vite.close())
const { TwinMap } = await vite.ssrLoadModule('/src/twin/TwinMap.tsx')
const { Nav } = await vite.ssrLoadModule('/src/components/Nav.tsx')
const { DashboardPage } = await vite.ssrLoadModule('/src/routes/DashboardPage.tsx')
const { MemoryRouter } = await import('react-router-dom')
const track = { segments: [
  { segment: 0, points: [
    { seq_id: 1, east_m: 0, north_m: 0, delivery: 'realtime' },
    { seq_id: 2, east_m: 0, north_m: 1, delivery: 'realtime' },
  ] },
  { segment: 1, points: [
    { seq_id: 3, east_m: 2, north_m: 2, delivery: 'backfilled' },
    { seq_id: 4, east_m: 3, north_m: 2, delivery: 'backfilled' },
  ] },
] }
const pins = { pins: [], unlocalized: [{ label: 'unlocalized-only' }], marker: {
  status: 'current', note: 'live phone-camera pose', pose: { x_m: 3, z_m: -2, yaw_rad: Math.PI / 2 },
} }
const render = (stale = false) => renderToStaticMarkup(createElement(TwinMap, { track, pins, stale }))

test('the website header links to the dashboard and its pane renders the twin', () => {
  const page = renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: ['/dashboard'] }, createElement(Nav), createElement(DashboardPage)))
  assert.match(page, /href="\/dashboard"/)
  assert.match(page, /Site requirements/)
  assert.match(page, /Incoming frames/)
  assert.match(page, /Backend logs/)
  assert.match(page, /Detection confidence/)
  assert.match(page, /aria-label="Digital twin"/)
  assert.match(page, /Connection settings/)
})

test('tracking gaps are not bridged and backfilled segments are visibly distinct', () => {
  const svg = render()
  assert.equal((svg.match(/<line /g) || []).length, 2)
  assert.match(svg, /stroke-dasharray="6 5"/)
  assert.doesNotMatch(svg, /unlocalized-only/)
})

test('left turn points west and a stale response cannot claim a current camera', () => {
  assert.match(render(), /rotate\(-90\)/)
  const stale = render(true)
  assert.match(stale, /Data is stale/)
  assert.match(stale, /Last known phone camera; current position unknown/)
  assert.doesNotMatch(stale, /Current phone camera/)
})

test('pin labels are escaped rather than interpreted as markup', () => {
  const svg = renderToStaticMarkup(createElement(TwinMap, { track, stale: false, pins: {
    ...pins, pins: [{ id: 'a', kind: 'evidence', label: '<script>bad</script>', east_m: 0, north_m: 0, source_mode: 'SAMPLE', delivery: 'realtime' }],
  } }))
  assert.doesNotMatch(svg, /<script>/)
  assert.match(svg, /&lt;script&gt;/)
})
