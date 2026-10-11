import type { RefObject } from 'react'
import {
  BoxGeometry,
  ConeGeometry,
  CylinderGeometry,
  MeshStandardMaterial,
  PlaneGeometry,
  type Group,
  type Mesh,
} from 'three'
import { palette } from './palette.ts'
import { PHONE_FORWARD, PHONE_HEIGHT, WHEEL_RADIUS } from './timeline.ts'
import { shadowMaterial, sightMaterial } from './materials.ts'

const SIGHT_LENGTH = 6.2
const SIGHT_RADIUS = 3.4

const unit = new BoxGeometry(1, 1, 1)
const wheel = new CylinderGeometry(WHEEL_RADIUS, WHEEL_RADIUS, 0.14, 20)
const hub = new BoxGeometry(0.15, 0.26, 0.05)
const lidar = new CylinderGeometry(0.09, 0.09, 0.08, 16)
const lens = new CylinderGeometry(0.018, 0.018, 0.012, 12)
const sightGeometry = new ConeGeometry(SIGHT_RADIUS, SIGHT_LENGTH, 40, 1, true)
const blob = new PlaneGeometry(1.4, 1.9)

const m = {
  body: new MeshStandardMaterial({ color: palette.rover, roughness: 0.55 }),
  accent: new MeshStandardMaterial({ color: palette.roverAccent, roughness: 0.5 }),
  dark: new MeshStandardMaterial({ color: palette.roverDark, roughness: 0.7 }),
  hub: new MeshStandardMaterial({ color: palette.hub, roughness: 0.5 }),
  phone: new MeshStandardMaterial({ color: palette.phone, roughness: 0.25, metalness: 0.3 }),
  status: new MeshStandardMaterial({ color: palette.sight, emissive: palette.sight, emissiveIntensity: 1.2 }),
}

const wheelSpots: Array<[number, number, number]> = [
  [-0.52, WHEEL_RADIUS, -0.42],
  [0.52, WHEEL_RADIUS, -0.42],
  [-0.52, WHEEL_RADIUS, 0.42],
  [0.52, WHEEL_RADIUS, 0.42],
]

type RoverProps = {
  body: RefObject<Group | null>
  wheels: RefObject<Array<Group | null>>
  sight: RefObject<Mesh | null>
}

function Part({ at, size, material }: { at: [number, number, number]; size: [number, number, number]; material: MeshStandardMaterial }) {
  return <mesh geometry={unit} material={material} position={at} scale={size} />
}

export function Rover({ body, wheels, sight }: RoverProps) {
  return (
    <group ref={body}>
      <mesh geometry={blob} material={shadowMaterial()} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.006, 0]} />
      <Part at={[0, 0.4, 0]} size={[0.9, 0.3, 1.3]} material={m.body} />
      <Part at={[0, 0.33, 0]} size={[0.92, 0.05, 1.32]} material={m.accent} />
      <Part at={[0, 0.575, 0.05]} size={[0.8, 0.05, 1.05]} material={m.dark} />
      <Part at={[0, 0.3, -0.68]} size={[0.94, 0.12, 0.08]} material={m.dark} />
      <Part at={[0, 0.3, 0.68]} size={[0.94, 0.12, 0.08]} material={m.dark} />
      <Part at={[0, 0.46, -0.655]} size={[0.5, 0.03, 0.02]} material={m.status} />
      <mesh geometry={lidar} material={m.dark} position={[0, 0.64, 0.25]} />
      {wheelSpots.map((spot, index) => (
        <group
          key={spot.join(':')}
          position={spot}
          ref={(node) => {
            wheels.current[index] = node
          }}
        >
          <mesh geometry={wheel} material={m.dark} rotation={[0, 0, Math.PI / 2]} />
          <mesh geometry={hub} material={m.hub} position={[spot[0] > 0 ? 0.075 : -0.075, 0, 0]} />
        </group>
      ))}
      <Part at={[0, (0.6 + PHONE_HEIGHT) / 2, PHONE_FORWARD + 0.05]} size={[0.06, PHONE_HEIGHT - 0.6, 0.06]} material={m.dark} />
      <Part at={[0, PHONE_HEIGHT - 0.11, PHONE_FORWARD + 0.02]} size={[0.13, 0.05, 0.04]} material={m.dark} />
      <Part at={[0, PHONE_HEIGHT, PHONE_FORWARD]} size={[0.09, 0.18, 0.012]} material={m.phone} />
      <mesh geometry={lens} material={m.dark} position={[-0.025, PHONE_HEIGHT + 0.06, PHONE_FORWARD - 0.008]} rotation={[Math.PI / 2, 0, 0]} />
      <mesh
        ref={sight}
        geometry={sightGeometry}
        material={sightMaterial}
        position={[0, PHONE_HEIGHT, PHONE_FORWARD - SIGHT_LENGTH / 2]}
        rotation={[Math.PI / 2, 0, 0]}
      />
    </group>
  )
}
