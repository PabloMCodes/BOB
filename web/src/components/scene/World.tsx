import { useMemo } from 'react'
import {
  BoxGeometry,
  CylinderGeometry,
  DoubleSide,
  ExtrudeGeometry,
  MeshBasicMaterial,
  MeshStandardMaterial,
  PlaneGeometry,
  Shape,
} from 'three'
import { palette } from './palette.ts'
import { gravelTexture, skyTexture, stripeTexture } from './textures.ts'
import { FULL_PPE, netMaterial, shadowMaterial } from './materials.ts'
import { Worker } from './Worker.tsx'
import { marks } from './timeline.ts'

type Vec3 = [number, number, number]

const matte = (color: string, roughness = 0.9) => new MeshStandardMaterial({ color, roughness })

const m = {
  lane: matte(palette.lane, 1),
  laneLine: matte(palette.laneLine, 0.8),
  track: matte(palette.track, 1),
  walkway: matte(palette.walkway, 1),
  walkwayLine: matte(palette.walkwayLine, 0.7),
  slab: matte(palette.slab, 0.95),
  steel: matte(palette.steel, 0.55),
  primer: matte(palette.primer, 0.7),
  tube: matte(palette.scaffoldTube, 0.4),
  plank: matte(palette.plank),
  wood: matte(palette.wood),
  block: matte(palette.block),
  rebar: matte(palette.rebar, 0.6),
  barrier: matte(palette.barrier),
  barrierRed: matte(palette.barrierRed, 0.6),
  cone: matte(palette.cone, 0.6),
  coneBand: matte(palette.coneBand, 0.4),
  screen: new MeshStandardMaterial({ color: palette.fenceScreen, roughness: 1, side: DoubleSide }),
  post: matte(palette.fencePost, 0.5),
  excavator: matte(palette.excavator, 0.5),
  dark: matte(palette.machineDark, 0.7),
  crane: matte(palette.crane, 0.7),
  tape: matte(palette.tape, 0.55),
  tapePost: matte(palette.post, 0.6),
  container: matte(palette.container, 0.75),
  glass: new MeshStandardMaterial({ color: palette.glass, roughness: 0.2, metalness: 0.2 }),
  flood: new MeshStandardMaterial({ color: palette.flood, emissive: palette.flood, emissiveIntensity: 1.6 }),
  beacon: new MeshStandardMaterial({ color: palette.beacon, emissive: palette.beacon, emissiveIntensity: 2 }),
}

const unit = new BoxGeometry(1, 1, 1)
const plane = new PlaneGeometry(1, 1)
const tube = new CylinderGeometry(0.035, 0.035, 1, 8)

function Box({ at, size, material, rotation }: { at: Vec3; size: Vec3; material: MeshStandardMaterial; rotation?: Vec3 }) {
  return <mesh geometry={unit} material={material} position={at} scale={size} rotation={rotation} />
}

function Flat({ at, size, material, rotation = 0 }: { at: Vec3; size: [number, number]; material: MeshStandardMaterial | MeshBasicMaterial; rotation?: number }) {
  return (
    <mesh
      geometry={plane}
      material={material}
      position={at}
      rotation={[-Math.PI / 2, 0, rotation]}
      scale={[size[0], size[1], 1]}
    />
  )
}

function Tube({ from, to }: { from: Vec3; to: Vec3 }) {
  const dx = to[0] - from[0]
  const dy = to[1] - from[1]
  const dz = to[2] - from[2]
  const length = Math.hypot(dx, dy, dz)
  const mid: Vec3 = [(from[0] + to[0]) / 2, (from[1] + to[1]) / 2, (from[2] + to[2]) / 2]
  const rotation: Vec3 =
    Math.abs(dy) > 0.99 * length
      ? [0, 0, 0]
      : Math.abs(dx) > Math.abs(dz)
        ? [0, 0, Math.PI / 2]
        : [Math.PI / 2, 0, 0]
  return <mesh geometry={tube} material={m.tube} position={mid} rotation={rotation} scale={[1, length, 1]} />
}

function Shadow({ at, size }: { at: Vec3; size: [number, number] }) {
  return <Flat at={[at[0], at[1] + 0.004, at[2]]} size={size} material={shadowMaterial()} />
}

function Ground() {
  const gravel = useMemo(
    () => new MeshStandardMaterial({ color: palette.gravel, roughness: 1, map: gravelTexture() }),
    [],
  )
  const sky = useMemo(() => new MeshBasicMaterial({ map: skyTexture(), fog: false }), [])
  return (
    <group>
      <Flat at={[0, 0, -2]} size={[64, 46]} material={gravel} />
      <mesh geometry={plane} material={sky} position={[0, 13, -34]} scale={[150, 34, 1]} />
      <Flat at={[0, 0.008, -0.5]} size={[1.6, 18]} material={m.lane} />
      {Array.from({ length: 18 }, (_, index) => 8 - index).map((z) => (
        <group key={z}>
          <Flat at={[-0.8, 0.012, z]} size={[0.06, 0.55]} material={m.laneLine} />
          <Flat at={[0.8, 0.012, z]} size={[0.06, 0.55]} material={m.laneLine} />
        </group>
      ))}
      <Flat at={[-0.42, 0.01, -0.5]} size={[0.16, 18]} material={m.track} />
      <Flat at={[0.42, 0.01, -0.5]} size={[0.16, 18]} material={m.track} />
      <Flat at={[6.4, 0.006, 3.2]} size={[0.5, 7]} material={m.track} rotation={0.5} />
      <Flat at={[7.6, 0.006, 3.6]} size={[0.5, 7]} material={m.track} rotation={0.5} />
    </group>
  )
}

function SlabAndFrame() {
  const columns: Array<[number, number]> = []
  for (const x of [-6.6, -4.8, -3.0]) for (const z of [-3.5, -1.0]) columns.push([x, z])
  return (
    <group>
      <Box at={[-4.15, 0.09, -2.2]} size={[5.7, 0.18, 3.2]} material={m.slab} />
      {columns.map(([x, z]) => (
        <Box key={`${x}:${z}`} at={[x, 0.18 + 1.8, z]} size={[0.16, 3.6, 0.16]} material={m.steel} />
      ))}
      {[-3.5, -1.0].map((z) => (
        <Box key={`bx${z}`} at={[-4.8, 3.66, z]} size={[3.95, 0.22, 0.14]} material={m.primer} />
      ))}
      {[-6.6, -4.8, -3.0].map((x) => (
        <Box key={`bz${x}`} at={[x, 3.66, -2.25]} size={[0.14, 0.22, 2.65]} material={m.primer} />
      ))}
      <Box at={[-4.8, 2.0, -3.5]} size={[3.95, 0.18, 0.12]} material={m.primer} />
      {[0, 1, 2, 3, 4].map((index) => (
        <Box key={`rb${index}`} at={[-5.6 + index * 0.08, 0.2, -2.3]} size={[0.025, 0.025, 2.2]} material={m.rebar} />
      ))}
    </group>
  )
}

function RestrictedZone() {
  const stripes = useMemo(
    () => new MeshStandardMaterial({ map: stripeTexture(), roughness: 0.6, side: DoubleSide }),
    [],
  )
  const cx = 2.7
  const cz = -0.8
  const w = 2.2
  const d = 2.0
  const corners: Array<[number, number]> = [
    [cx - w / 2, cz - d / 2],
    [cx + w / 2, cz - d / 2],
    [cx + w / 2, cz + d / 2],
    [cx - w / 2, cz + d / 2],
  ]
  return (
    <group>
      <Flat at={[cx, 0.014, cz - d / 2]} size={[w, 0.09]} material={m.tape} />
      <Flat at={[cx, 0.014, cz + d / 2]} size={[w, 0.09]} material={m.tape} />
      <Flat at={[cx - w / 2, 0.014, cz]} size={[0.09, d]} material={m.tape} />
      <Flat at={[cx + w / 2, 0.014, cz]} size={[0.09, d]} material={m.tape} />
      {corners.map(([x, z]) => (
        <group key={`${x}:${z}`}>
          <mesh geometry={tube} material={m.tapePost} position={[x, 0.5, z]} scale={[1.1, 1, 1.1]} />
          <Box at={[x, 0.02, z]} size={[0.22, 0.04, 0.22]} material={m.dark} />
        </group>
      ))}
      {corners.map(([x, z], index) => {
        const [nx, nz] = corners[(index + 1) % corners.length]
        const length = Math.hypot(nx - x, nz - z)
        const angle = Math.atan2(nz - z, nx - x)
        return (
          <mesh
            key={`t${index}`}
            geometry={plane}
            material={stripes}
            position={[(x + nx) / 2, 0.93, (z + nz) / 2]}
            rotation={[0, -angle, 0]}
            scale={[length, 0.07, 1]}
          />
        )
      })}
    </group>
  )
}

function Walkway() {
  return (
    <group>
      <Flat at={[-4.45, 0.01, -4.8]} size={[7.1, 1.3]} material={m.walkway} />
      <Flat at={[-4.45, 0.014, -4.15]} size={[7.1, 0.07]} material={m.walkwayLine} />
      <Flat at={[-4.45, 0.014, -5.45]} size={[7.1, 0.07]} material={m.walkwayLine} />
      {[-7.2, -5.6, -4.0].map((x) => (
        <Flat key={x} at={[x, 0.014, -4.8]} size={[0.5, 0.12]} material={m.walkwayLine} />
      ))}
      <Shadow at={[-2.6, 0, -4.8]} size={[1.7, 1.5]} />
      <Box at={[-2.6, 0.065, -4.8]} size={[1.15, 0.13, 1.0]} material={m.wood} />
      <Box at={[-2.62, 0.5, -4.8]} size={[1.05, 0.74, 0.9]} material={m.block} />
      <Box at={[-2.2, 0.065, -4.45]} size={[0.8, 0.13, 0.7]} material={m.wood} />
      <Box at={[-2.2, 0.98, -4.6]} size={[0.6, 0.22, 0.5]} material={m.block} />
    </group>
  )
}

function JerseyBarrier({ at, rotation = 0 }: { at: Vec3; rotation?: number }) {
  const geometry = useMemo(() => {
    const profile = new Shape()
    profile.moveTo(-0.3, 0)
    profile.lineTo(0.3, 0)
    profile.lineTo(0.18, 0.25)
    profile.lineTo(0.1, 0.8)
    profile.lineTo(-0.1, 0.8)
    profile.lineTo(-0.18, 0.25)
    profile.closePath()
    const result = new ExtrudeGeometry(profile, { depth: 1.9, bevelEnabled: false })
    result.translate(0, 0, -0.95)
    return result
  }, [])
  return (
    <group position={at} rotation={[0, rotation, 0]}>
      <Shadow at={[0, 0, 0]} size={[1.0, 2.3]} />
      <mesh geometry={geometry} material={m.barrier} />
    </group>
  )
}

function Materials() {
  return (
    <group>
      <Shadow at={[-2.0, 0, -6.7]} size={[2.6, 1.8]} />
      <Box at={[-2.4, 0.065, -6.7]} size={[1.15, 0.13, 1.0]} material={m.wood} />
      <Box at={[-2.4, 0.5, -6.7]} size={[1.05, 0.74, 0.9]} material={m.block} />
      {[0, 1, 2, 3, 4].map((index) => (
        <Box key={index} at={[-1.25, 0.08 + index * 0.13, -6.75]} size={[1.0, 0.11, 0.95]} material={m.wood} />
      ))}
      <JerseyBarrier at={[-4.2, 0, -6.9]} rotation={Math.PI / 2} />
      <JerseyBarrier at={[0.2, 0, -6.95]} rotation={Math.PI / 2} />
    </group>
  )
}

function Scaffolding() {
  const xs = [3.0, 4.0, 5.0]
  const zs = [-3.6, -4.4]
  const levels = [1.0, 2.0, 3.0, 4.0]
  return (
    <group>
      {xs.flatMap((x) => zs.map((z) => <Tube key={`s${x}${z}`} from={[x, 0, z]} to={[x, 4.3, z]} />))}
      {zs.flatMap((z) => levels.map((y) => <Tube key={`l${z}${y}`} from={[3.0, y, z]} to={[5.0, y, z]} />))}
      {xs.flatMap((x) => levels.map((y) => <Tube key={`t${x}${y}`} from={[x, y, -3.6]} to={[x, y, -4.4]} />))}
      {[2.0, 4.0].map((y) => (
        <Box key={`p${y}`} at={[4.0, y + 0.04, -4.0]} size={[2.0, 0.05, 0.8]} material={m.plank} />
      ))}
      <mesh geometry={plane} material={netMaterial} position={[4.0, 2.55, -3.55]} scale={[2.0, 3.3, 1]} />
    </group>
  )
}

function Cone({ at }: { at: Vec3 }) {
  return (
    <group position={at}>
      <Box at={[0, 0.015, 0]} size={[0.32, 0.03, 0.32]} material={m.cone} />
      <mesh position={[0, 0.25, 0]} material={m.cone}>
        <coneGeometry args={[0.15, 0.45, 16]} />
      </mesh>
      <mesh position={[0, 0.27, 0]} material={m.coneBand}>
        <cylinderGeometry args={[0.083, 0.098, 0.07, 16, 1, true]} />
      </mesh>
    </group>
  )
}

function Fence() {
  const posts = Array.from({ length: 13 }, (_, index) => -15 + index * 2.5)
  return (
    <group>
      <mesh geometry={plane} material={m.screen} position={[0, 1.0, -9.6]} scale={[30, 1.9, 1]} />
      {posts.map((x) => (
        <Box key={x} at={[x, 1.0, -9.55]} size={[0.07, 2.0, 0.07]} material={m.post} />
      ))}
    </group>
  )
}

function Crane() {
  return (
    <group position={[-13, 0, -21]}>
      <Box at={[0, 9, 0]} size={[0.9, 18, 0.9]} material={m.crane} />
      <Box at={[5.5, 18.4, 0]} size={[15, 0.55, 0.55]} material={m.crane} />
      <Box at={[-4.0, 18.4, 0]} size={[5, 0.55, 0.55]} material={m.crane} />
      <Box at={[-5.8, 17.6, 0]} size={[1.4, 1.4, 1.2]} material={m.dark} />
      <Box at={[0, 19.4, 0]} size={[0.4, 2.0, 0.4]} material={m.crane} />
      <Box at={[0.9, 17.4, 0]} size={[1.0, 1.0, 1.0]} material={m.dark} />
      <Box at={[9.5, 13.5, 0]} size={[0.04, 9.4, 0.04]} material={m.dark} />
      <Box at={[9.5, 8.6, 0]} size={[0.5, 0.4, 0.5]} material={m.excavator} />
      <mesh position={[0, 20.5, 0]} material={m.beacon}>
        <sphereGeometry args={[0.18, 8, 6]} />
      </mesh>
    </group>
  )
}

function Excavator() {
  return (
    <group position={[7.4, 0, 2.2]} rotation={[0, -0.75, 0]}>
      <Shadow at={[0, 0, 0]} size={[3.6, 3.4]} />
      <Box at={[0, 0.3, 0.75]} size={[2.8, 0.6, 0.55]} material={m.dark} />
      <Box at={[0, 0.3, -0.75]} size={[2.8, 0.6, 0.55]} material={m.dark} />
      <Box at={[0.1, 1.0, 0]} size={[2.2, 0.8, 1.9]} material={m.excavator} />
      <Box at={[0.55, 1.85, 0.45]} size={[0.95, 0.95, 0.85]} material={m.excavator} />
      <Box at={[0.8, 1.9, 0.45]} size={[0.5, 0.65, 0.88]} material={m.glass} />
      <Box at={[-0.9, 1.35, 0]} size={[0.6, 0.5, 1.7]} material={m.dark} />
      <Box at={[1.75, 2.2, -0.2]} size={[2.4, 0.32, 0.32]} material={m.excavator} rotation={[0, 0, 0.55]} />
      <Box at={[3.0, 1.55, -0.2]} size={[0.28, 1.9, 0.28]} material={m.excavator} rotation={[0, 0, -0.25]} />
      <Box at={[3.25, 0.45, -0.2]} size={[0.6, 0.45, 0.7]} material={m.dark} rotation={[0, 0, 0.4]} />
    </group>
  )
}

function Floodlight() {
  return (
    <group position={[6.8, 0, -7.2]}>
      <Box at={[0, 0.45, 0]} size={[1.4, 0.7, 0.9]} material={m.excavator} />
      <Box at={[0, 3.6, 0]} size={[0.12, 6.0, 0.12]} material={m.post} />
      <Box at={[0, 6.6, 0.1]} size={[1.3, 0.5, 0.12]} material={m.flood} rotation={[-0.5, 0, 0]} />
    </group>
  )
}

function Container() {
  return (
    <group position={[-9.2, 0, 2.6]}>
      <Shadow at={[0, 0, 0]} size={[3.2, 6.8]} />
      <Box at={[0, 1.3, 0]} size={[2.4, 2.6, 6.0]} material={m.container} />
      <Box at={[1.21, 1.3, 1.2]} size={[0.02, 0.9, 1.4]} material={m.glass} />
    </group>
  )
}

function Workers() {
  const at = Object.fromEntries(marks.map((mark) => [mark.id, [mark.x, mark.base, mark.z] as Vec3]))
  return (
    <group>
      <Worker position={at.eyewear} facing={0.7} ppe={{ ...FULL_PPE, glasses: false }} />
      <Worker position={at.helmet} facing={0.9} ppe={{ ...FULL_PPE, helmet: false }} vest="orange" />
      <Worker position={at.path} facing={-1.4} ppe={FULL_PPE} tablet helmet="yellow" />
      <Worker position={at.zone} facing={-0.6} ppe={FULL_PPE} vest="orange" />
      <Worker position={at.occluded} facing={0.2} ppe={FULL_PPE} helmet="yellow" />
      <Worker position={at.clear} facing={-2.4} ppe={FULL_PPE} />
    </group>
  )
}

export function World() {
  return (
    <group>
      <Ground />
      <SlabAndFrame />
      <RestrictedZone />
      <Walkway />
      <Materials />
      <Scaffolding />
      <Fence />
      <Crane />
      <Excavator />
      <Floodlight />
      <Container />
      <JerseyBarrier at={[-1.5, 0, 5.0]} />
      <Cone at={[1.15, 0, 1.6]} />
      <Cone at={[1.15, 0, 0.4]} />
      <Cone at={[-1.15, 0, 6.8]} />
      <Cone at={[4.2, 0, 0.6]} />
      <Workers />
    </group>
  )
}
