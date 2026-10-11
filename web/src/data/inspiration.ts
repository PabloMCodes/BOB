export type JourneyPhoto = {
  src: string | null
  caption: string
  alt?: string
}

export type JourneyChapter = {
  id: string
  title: string
  /** Leave null until the team supplies this part of the story. */
  story: string | null
  storyPrompt?: string
  /** One image per step; a null `src` renders the "photo to come" placeholder. */
  photo: JourneyPhoto
  teamwork?: {
    challenge: string
    response: string
    /** Suggested mitigation copy must stay marked as a draft until confirmed. */
    responseStatus: 'draft' | 'confirmed'
  }
}

const robotPhoto = (number: number) => `/media/robot/photo_${number}_2026-10-11_01-56-30.jpg`

export type TeamOrigin = {
  id: 'mexico' | 'venezuela' | 'pakistan'
  name: string
  firstName: string
  initials: string
  country: string
  coordinates: [longitude: number, latitude: number]
}

/** Country mapping confirmed by the team; these are approximate country markers. */
export const teamOrigins: TeamOrigin[] = [
  { id: 'venezuela', name: 'Humberto Bohorquez', firstName: 'Humberto', initials: 'HB', country: 'Venezuela', coordinates: [-66, 7] },
  { id: 'mexico', name: 'Pablo Mendoza', firstName: 'Pablo', initials: 'PM', country: 'Mexico', coordinates: [-102, 24] },
  { id: 'pakistan', name: 'Maham Mehmood', firstName: 'Maham', initials: 'MM', country: 'Pakistan', coordinates: [69, 30] },
]

export const floridaCoordinates: [longitude: number, latitude: number] = [-82, 28]

/** The first three stories are intentionally left open. The first two images are reference
 * photographs of other companies' robots, not our build — the captions must keep saying so. */
export const inspirationChapters: JourneyChapter[] = [
  {
    id: 'the-problem',
    title: 'The problem we saw.',
    story: null,
    storyPrompt: 'The observation that started it all.',
    photo: {
      src: '/media/inspiration/warehouse-robot-fleet.jpg',
      caption: 'Reference: Amazon warehouse drive units',
      alt: 'A warehouse floor filled with hundreds of blue robotic drive units carrying parcels beneath spiral conveyors.',
    },
  },
  {
    id: 'the-idea',
    title: 'An idea called B.O.B.',
    story: null,
    storyPrompt: 'Our first ideas, sketches and conversations.',
    photo: {
      src: '/media/inspiration/construction-layout-robot.jpg',
      caption: 'Reference: a Dusty Robotics layout robot',
      alt: 'A small grey and orange Dusty Robotics layout robot printing dimensioned framing lines onto a concrete construction floor.',
    },
  },
  {
    id: 'the-design',
    title: 'Giving the idea a shape.',
    story: null,
    storyPrompt: 'The design choices and the reasons behind them.',
    photo: { src: robotPhoto(3), caption: 'Parts taking shape', alt: 'White rover parts on the bed of a 3D printer.' },
  },
  {
    id: 'the-build',
    title: 'The workbench chapter.',
    story: 'Laptops, components, tools and printed parts share a workbench as the physical build comes together.',
    photo: { src: robotPhoto(1), caption: 'Where the build comes together', alt: 'A workbench with laptops, wires, tools and the rover chassis during assembly.' },
    teamwork: {
      challenge: 'A 3D print failed midway. Starting again meant going back to zero and another roughly four hours of printing before the part would be ready.',
      response: 'We restarted the print and used the wait to move other work forward. Splitting the remaining wiring, software and assembly checks between us kept the whole team from waiting on one part.',
      responseStatus: 'draft',
    },
  },
  {
    id: 'the-connections',
    title: 'Connecting the pieces.',
    story: 'The software connects phone capture, Python vision and the operator dashboard. The onboard computer is part of the next deployment step.',
    photo: { src: robotPhoto(2), caption: 'The onboard computer', alt: 'A compact development board with a cooling fan, connected cables and a separate heatsink on the workbench.' },
    teamwork: {
      challenge: 'The Jetson brought a power-conversion challenge: the rover’s available supply had to become a suitable input for the onboard computer.',
      response: 'We separated the power checks from the rest of the build, reviewed the converter and connections together, and tested the supply before reconnecting the full system.',
      responseStatus: 'draft',
    },
  },
  {
    id: 'the-rover',
    title: 'An idea, now on wheels.',
    story: 'The current rover brings a chassis, wheels, batteries and wired electronics together. There is room here for the final build and the next round of testing.',
    photo: { src: robotPhoto(5), caption: 'B.O.B / the current build', alt: 'The assembled rover chassis with wheels, batteries, a breadboard and wired electronics on the workbench.' },
    teamwork: {
      challenge: 'With limited robotics experience, we had to connect the ESP32, wheel drive and encoders into one working system. Making the wheels respond while reading their movement was a new integration challenge.',
      response: 'We broke the problem into smaller tests: one wheel, one encoder and one ESP32 connection at a time. Comparing results together helped us separate wiring, control-code and feedback issues before combining the pieces.',
      responseStatus: 'draft',
    },
  },
]
