import { DoubleSide, MeshBasicMaterial, MeshStandardMaterial } from 'three'
import { palette } from './palette.ts'
import { blobTexture } from './textures.ts'

export type Ppe = {
  helmet: boolean
  vest: boolean
  gloves: boolean
  glasses: boolean
  boots: boolean
}

export const FULL_PPE: Ppe = { helmet: true, vest: true, gloves: true, glasses: true, boots: true }

let blobMaterial: MeshBasicMaterial | null = null
export function shadowMaterial() {
  blobMaterial ??= new MeshBasicMaterial({
    map: blobTexture(),
    transparent: true,
    depthWrite: false,
    opacity: 0.85,
  })
  return blobMaterial
}

export const netMaterial = new MeshStandardMaterial({
  color: palette.net,
  roughness: 1,
  transparent: true,
  opacity: 0.62,
  side: DoubleSide,
  depthWrite: false,
})

export const sightMaterial = new MeshBasicMaterial({
  color: palette.sight,
  transparent: true,
  opacity: 0.07,
  depthWrite: false,
  side: DoubleSide,
})
