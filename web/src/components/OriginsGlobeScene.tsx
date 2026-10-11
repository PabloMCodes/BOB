import { useEffect, useMemo, useRef } from 'react'
import { Canvas, useFrame, useLoader, useThree } from '@react-three/fiber'
import { CatmullRomCurve3, Color, MathUtils, TextureLoader, Vector3 } from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { floridaCoordinates, teamOrigins, type TeamOrigin } from '../data/inspiration.ts'

type GlobeSceneProps = {
  selected: TeamOrigin['id'] | null
  spinning: boolean
  visible: boolean
  reduced: boolean
  turn: number
}

function position([longitude, latitude]: [number, number], radius = 1) {
  const lon = MathUtils.degToRad(longitude)
  const lat = MathUtils.degToRad(latitude)
  return new Vector3(Math.cos(lat) * Math.cos(lon), Math.sin(lat), -Math.cos(lat) * Math.sin(lon)).multiplyScalar(radius)
}

/** Shortest great-circle route, lifted above the surface and attached at both ends. */
function connection(coordinates: [number, number]) {
  const start = position(coordinates)
  const end = position(floridaCoordinates)
  const angle = start.angleTo(end)
  const points = Array.from({ length: 65 }, (_, index) => {
    const t = index / 64
    const point = start.clone().multiplyScalar(Math.sin((1 - t) * angle))
      .addScaledVector(end, Math.sin(t * angle)).divideScalar(Math.sin(angle))
    return point.normalize().multiplyScalar(1.014 + Math.sin(Math.PI * t) * 0.22)
  })
  return new CatmullRomCurve3(points)
}

function themeColor(token: string) {
  return new Color(getComputedStyle(document.documentElement).getPropertyValue(`--color-${token}`).trim())
}

function RouteArc({ origin, active, selected, ink, muted }: {
  origin: TeamOrigin
  active: boolean
  selected: boolean
  ink: Color
  muted: Color
}) {
  const curve = useMemo(() => connection(origin.coordinates), [origin.coordinates])
  if (selected && !active) return null
  return (
    <group>
      <mesh>
        <tubeGeometry args={[curve, 64, active ? 0.005 : 0.002, 6, false]} />
        <meshBasicMaterial color={active ? ink : muted} transparent opacity={active ? 1 : 0.35} />
      </mesh>
      <mesh position={position(origin.coordinates, 1.016)}>
        <sphereGeometry args={[active ? 0.019 : 0.009, 12, 12]} />
        <meshBasicMaterial color={active ? ink : muted} />
      </mesh>
    </group>
  )
}

function World({ selected, spinning, reduced, turn }: GlobeSceneProps) {
  const { camera, gl, invalidate } = useThree()
  const controls = useRef<OrbitControls | null>(null)
  const destination = useRef<Vector3 | null>(null)
  const previousTurn = useRef(turn)
  const maps = useLoader(TextureLoader, [
    '/media/globe/land.svg', '/media/globe/venezuela.svg',
    '/media/globe/mexico.svg', '/media/globe/pakistan.svg',
  ])
  const colors = useMemo(() => ({ ocean: themeColor('plate'), land: themeColor('line'), ink: themeColor('ink'), muted: themeColor('muted') }), [])
  const person = teamOrigins.find(origin => origin.id === selected)
  const selectedMap = person ? maps[teamOrigins.indexOf(person) + 1] : null

  useEffect(() => {
    const orbit = new OrbitControls(camera, gl.domElement)
    orbit.enableZoom = false
    orbit.enablePan = false
    orbit.enableDamping = false
    orbit.autoRotateSpeed = 0.5
    orbit.minPolarAngle = Math.PI * 0.12
    orbit.maxPolarAngle = Math.PI * 0.88
    const dragStart = () => { destination.current = null }
    const changed = () => invalidate()
    orbit.addEventListener('start', dragStart)
    orbit.addEventListener('change', changed)
    controls.current = orbit
    orbit.update()
    return () => {
      orbit.removeEventListener('start', dragStart)
      orbit.removeEventListener('change', changed)
      orbit.dispose()
      controls.current = null
    }
  }, [camera, gl, invalidate])

  useEffect(() => {
    const view = person
      ? position(person.coordinates).add(position(floridaCoordinates)).normalize().multiplyScalar(3.8)
      : position([-15, 20], 3.8)
    if (reduced) {
      camera.position.copy(view)
      controls.current?.update()
    } else destination.current = view
    invalidate()
  }, [person, reduced, camera, invalidate])

  useEffect(() => {
    const angle = (turn - previousTurn.current) * Math.PI / 8
    previousTurn.current = turn
    destination.current = null
    camera.position.applyAxisAngle(new Vector3(0, 1, 0), angle)
    controls.current?.update()
    invalidate()
  }, [turn, camera, invalidate])

  useFrame((_, delta) => {
    const orbit = controls.current
    if (!orbit) return
    if (destination.current) {
      camera.position.lerp(destination.current, 1 - Math.exp(-Math.min(delta, 0.1) * 5))
      camera.position.normalize().multiplyScalar(3.8)
      if (camera.position.distanceTo(destination.current) < 0.003) {
        camera.position.copy(destination.current)
        destination.current = null
      } else invalidate()
    }
    orbit.autoRotate = spinning && !destination.current
    orbit.update(delta)
  })

  return (
    <>
      <mesh><sphereGeometry args={[1, 64, 48]} /><meshBasicMaterial color={colors.ocean} /></mesh>
      <mesh><sphereGeometry args={[1.001, 64, 48]} /><meshBasicMaterial map={maps[0]} color={colors.land} transparent depthWrite={false} /></mesh>
      {selectedMap ? <mesh><sphereGeometry args={[1.003, 64, 48]} /><meshBasicMaterial map={selectedMap} color={colors.ink} transparent depthWrite={false} /></mesh> : null}
      {teamOrigins.map(origin => <RouteArc key={origin.id} origin={origin} active={selected === origin.id} selected={selected !== null} ink={colors.ink} muted={colors.muted} />)}
      <mesh position={position(floridaCoordinates, 1.016)}><sphereGeometry args={[0.02, 16, 16]} /><meshBasicMaterial color={colors.ink} /></mesh>
    </>
  )
}

const globeCamera = { position: position([-15, 20], 3.8).toArray(), fov: 38, near: 0.1, far: 20 }

export function OriginsGlobeScene(props: GlobeSceneProps) {
  return (
    <Canvas camera={globeCamera} dpr={[1, 1.5]} frameloop={props.visible && props.spinning ? 'always' : 'demand'} gl={{ alpha: true, antialias: true }} aria-hidden="true">
      <World {...props} spinning={props.spinning && props.visible} />
    </Canvas>
  )
}
