import { CanvasTexture, RepeatWrapping, SRGBColorSpace } from 'three'
import { palette } from './palette.ts'

function canvas(width: number, height: number) {
  const node = document.createElement('canvas')
  node.width = width
  node.height = height
  const context = node.getContext('2d')
  if (!context) throw new Error('2D canvas unavailable')
  return { node, context }
}

function texture(node: HTMLCanvasElement, repeat?: [number, number]) {
  const result = new CanvasTexture(node)
  result.colorSpace = SRGBColorSpace
  if (repeat) {
    result.wrapS = RepeatWrapping
    result.wrapT = RepeatWrapping
    result.repeat.set(repeat[0], repeat[1])
  }
  return result
}

/** Deterministic speckle so the pad reads as gravel, not a flat plane. */
export function gravelTexture() {
  const size = 256
  const { node, context } = canvas(size, size)
  context.fillStyle = '#ffffff'
  context.fillRect(0, 0, size, size)
  let seed = 7
  const random = () => {
    seed = (seed * 16807) % 2147483647
    return seed / 2147483647
  }
  for (let i = 0; i < 5200; i += 1) {
    const shade = 150 + Math.floor(random() * 105)
    context.fillStyle = `rgb(${shade} ${shade - 4} ${shade - 10})`
    const r = 0.6 + random() * 1.6
    context.beginPath()
    context.arc(random() * size, random() * size, r, 0, Math.PI * 2)
    context.fill()
  }
  return texture(node, [14, 10])
}

export function stripeTexture() {
  const { node, context } = canvas(128, 16)
  for (let i = 0; i < 8; i += 1) {
    context.fillStyle = i % 2 === 0 ? palette.tape : palette.tapeBlack
    context.beginPath()
    context.moveTo(i * 16, 16)
    context.lineTo(i * 16 + 16, 0)
    context.lineTo(i * 16 + 32, 0)
    context.lineTo(i * 16 + 16, 16)
    context.closePath()
    context.fill()
  }
  return texture(node, [4, 1])
}

/** Soft dark ellipse that stands in for a contact shadow. */
export function blobTexture() {
  const size = 64
  const { node, context } = canvas(size, size)
  const gradient = context.createRadialGradient(32, 32, 2, 32, 32, 32)
  gradient.addColorStop(0, 'rgba(0,0,0,0.75)')
  gradient.addColorStop(1, 'rgba(0,0,0,0)')
  context.fillStyle = gradient
  context.fillRect(0, 0, size, size)
  return texture(node)
}

export function skyTexture() {
  const { node, context } = canvas(4, 128)
  const gradient = context.createLinearGradient(0, 0, 0, 128)
  gradient.addColorStop(0, palette.skyTop)
  gradient.addColorStop(0.62, '#1a120c')
  gradient.addColorStop(1, palette.skyGlow)
  context.fillStyle = gradient
  context.fillRect(0, 0, 4, 128)
  return texture(node)
}
