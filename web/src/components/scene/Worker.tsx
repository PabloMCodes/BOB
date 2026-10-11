import {
  BoxGeometry,
  CapsuleGeometry,
  CylinderGeometry,
  MeshStandardMaterial,
  PlaneGeometry,
  SphereGeometry,
} from 'three'
import { palette } from './palette.ts'
import { shadowMaterial, type Ppe } from './materials.ts'

const matte = (color: string, roughness = 0.85) => new MeshStandardMaterial({ color, roughness })

const materials = {
  skin: matte(palette.skin),
  shirt: matte(palette.shirt),
  pants: matte(palette.pants),
  boots: matte(palette.boots),
  shoe: matte(palette.shoe),
  helmetWhite: matte(palette.helmetWhite, 0.45),
  helmetYellow: matte(palette.helmetYellow, 0.45),
  vestLime: new MeshStandardMaterial({ color: palette.vestLime, roughness: 0.6, emissive: palette.vestLime, emissiveIntensity: 0.08 }),
  vestOrange: new MeshStandardMaterial({ color: palette.vestOrange, roughness: 0.6, emissive: palette.vestOrange, emissiveIntensity: 0.08 }),
  stripe: new MeshStandardMaterial({ color: palette.vestStripe, roughness: 0.3, emissive: palette.vestStripe, emissiveIntensity: 0.15 }),
  glove: matte(palette.glove),
  glasses: matte(palette.glasses, 0.25),
  tablet: matte(palette.tablet, 0.4),
}

const geometry = {
  boot: new BoxGeometry(0.13, 0.11, 0.26),
  leg: new CapsuleGeometry(0.085, 0.56, 4, 10),
  torso: new CapsuleGeometry(0.17, 0.34, 4, 12),
  vest: new CylinderGeometry(0.188, 0.195, 0.44, 14, 1, true),
  stripe: new CylinderGeometry(0.197, 0.197, 0.035, 14, 1, true),
  arm: new CapsuleGeometry(0.055, 0.46, 4, 8),
  hand: new SphereGeometry(0.06, 10, 8),
  head: new SphereGeometry(0.12, 16, 12),
  helmet: new SphereGeometry(0.138, 16, 10, 0, Math.PI * 2, 0, Math.PI / 2),
  brim: new CylinderGeometry(0.168, 0.168, 0.018, 18),
  glasses: new BoxGeometry(0.17, 0.035, 0.03),
  tablet: new BoxGeometry(0.22, 0.3, 0.015),
  blob: new PlaneGeometry(0.9, 0.9),
}

type WorkerProps = {
  position: [number, number, number]
  facing?: number
  ppe: Ppe
  vest?: 'lime' | 'orange'
  helmet?: 'white' | 'yellow'
  tablet?: boolean
}

export function Worker({ position, facing = 0, ppe, vest = 'lime', helmet = 'white', tablet = false }: WorkerProps) {
  const vestMaterial = vest === 'lime' ? materials.vestLime : materials.vestOrange
  const handMaterial = ppe.gloves ? materials.glove : materials.skin
  const footMaterial = ppe.boots ? materials.boots : materials.shoe
  return (
    <group position={position} rotation={[0, facing, 0]}>
      <mesh geometry={geometry.blob} material={shadowMaterial()} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.006, 0]} />
      <mesh geometry={geometry.boot} material={footMaterial} position={[-0.1, 0.055, 0.03]} />
      <mesh geometry={geometry.boot} material={footMaterial} position={[0.1, 0.055, 0.03]} />
      <mesh geometry={geometry.leg} material={materials.pants} position={[-0.1, 0.48, 0]} />
      <mesh geometry={geometry.leg} material={materials.pants} position={[0.1, 0.48, 0]} />
      <mesh geometry={geometry.torso} material={materials.shirt} position={[0, 1.06, 0]} />
      {ppe.vest ? (
        <>
          <mesh geometry={geometry.vest} material={vestMaterial} position={[0, 1.1, 0]} />
          <mesh geometry={geometry.stripe} material={materials.stripe} position={[0, 0.98, 0]} />
          <mesh geometry={geometry.stripe} material={materials.stripe} position={[0, 1.13, 0]} />
        </>
      ) : null}
      <mesh geometry={geometry.arm} material={materials.shirt} position={[-0.25, 1.06, 0]} rotation={[0, 0, -0.08]} />
      <mesh geometry={geometry.arm} material={materials.shirt} position={[0.25, 1.06, 0]} rotation={[0, 0, 0.08]} />
      <mesh geometry={geometry.hand} material={handMaterial} position={[-0.28, 0.76, 0.02]} />
      <mesh geometry={geometry.hand} material={handMaterial} position={[0.28, 0.76, 0.02]} />
      {tablet ? (
        <mesh geometry={geometry.tablet} material={materials.tablet} position={[0.02, 1.02, 0.22]} rotation={[-0.9, 0, 0]} />
      ) : null}
      <mesh geometry={geometry.head} material={materials.skin} position={[0, 1.53, 0]} />
      {ppe.glasses ? <mesh geometry={geometry.glasses} material={materials.glasses} position={[0, 1.545, 0.112]} /> : null}
      {ppe.helmet ? (
        <>
          <mesh
            geometry={geometry.helmet}
            material={helmet === 'white' ? materials.helmetWhite : materials.helmetYellow}
            position={[0, 1.57, 0]}
          />
          <mesh
            geometry={geometry.brim}
            material={helmet === 'white' ? materials.helmetWhite : materials.helmetYellow}
            position={[0, 1.575, 0.012]}
          />
        </>
      ) : null}
    </group>
  )
}
