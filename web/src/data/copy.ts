export type Status = 'built' | 'dev'

export const statusLabel: Record<Status, string> = {
  built: 'Built',
  dev: 'In development',
}

export const copy = {
  wordmark: 'B.O.B',
  expansion: 'Building-site Observation Bot',
  nav: {
    product: 'Product',
    dashboard: 'Dashboard',
    github: 'GitHub',
  },
  links: {
    /** Leave empty to hide every GitHub link. */
    github: 'https://github.com/PabloMCodes/BOB',
  },
  hero: {
    title: 'A second set of eyes on every site walk.',
    body: 'B.O.B is an inspection robot for construction sites. It checks the people it sees for the PPE that site requires, watches taped-off zones, and hands the supervisor a record with the original frame behind every finding. What it could not see stays marked as unknown.',
    scroll: 'Scroll',
  },
  video: {
    /** The 11-character YouTube ID. Leave empty to show the placeholder frame. */
    youtubeId: '',
    title: 'B.O.B on a worksite',
    empty: 'Video coming soon',
  },
  overview: {
    eyebrow: 'What it is',
    statement:
      'An iPhone on the mast streams what B.O.B sees to the computer it carries. Vision models find people and the gear on them, check only what that worksite requires, and keep every finding with the frame it came from. Nothing unseen is reported as safe.',
  },
  skills: {
    eyebrow: 'Skills',
    title: 'What B.O.B does on a site walk.',
    cards: [
      {
        id: 'ppe',
        status: 'built',
        title: 'Sees people and their PPE.',
        body: 'Hard hat, vest, gloves, eyewear and boots, boxed on each person in frame.',
      },
      {
        id: 'eyewear',
        status: 'built',
        title: 'Checks eyewear from far away.',
        body: 'Full-resolution head crops, so a face across the site still gets looked at.',
      },
      {
        id: 'zones',
        status: 'built',
        title: 'Watches taped restricted zones.',
        body: 'Yellow floor tape is recognized, and a person standing inside it becomes a finding.',
      },
      {
        id: 'alerts',
        status: 'built',
        title: 'Raises an alert.',
        body: 'Repeated observations become a confirmed incident, with the evidence attached.',
      },
      {
        id: 'drive',
        status: 'dev',
        title: 'Drives itself.',
        body: 'The rover is becoming an autonomous inspection vehicle.',
      },
    ],
  },
  audience: {
    eyebrow: 'Who it helps',
    title: 'Built for the people who answer for the site.',
    tiles: [
      {
        title: 'Site safety managers',
        body: 'See which PPE checks were made on which person, and which ones the camera could not make.',
      },
      {
        title: 'Superintendents',
        body: 'Start the walk with the routine looking already on record.',
      },
      {
        title: 'Crews',
        body: 'The same check for everyone, recorded the same way.',
      },
      {
        title: 'Owners and inspectors',
        body: 'A record tied to the original frame, which a later change of rules cannot rewrite.',
      },
    ],
  },
  system: {
    eyebrow: 'How it works',
    title: 'From the camera to the supervisor’s screen.',
    nodes: [
      {
        index: '01',
        title: 'iPhone capture',
        body: 'Camera frames, timestamps and ARKit pose, streamed over the local network.',
        status: 'built',
      },
      {
        index: '02',
        title: 'Rover computer',
        body: 'Finds people and PPE, checks the site’s requirements and stores the evidence. A Mac today, a Jetson Orin Nano next.',
        status: 'built',
      },
      {
        index: '03',
        title: 'Operator laptop',
        body: 'A synced copy of every finding and its evidence works today. The dashboard and 2D Twin views are next.',
        status: 'dev',
      },
    ],
  },
  agents: {
    eyebrow: 'How the record is made',
    title: 'What the agents change for the people who rely on it.',
    steps: [
      {
        index: '01',
        title: 'Observe the frame.',
        body: 'People and PPE in that image.',
      },
      {
        index: '02',
        title: 'Assess the selected requirements.',
        body: 'Eyewear, helmet, gloves, high-visibility vest, and safety boots, only when that worksite required them.',
      },
      {
        index: '03',
        title: 'Keep the frame with the finding.',
        body: 'Evidence stays on the source frame, session, and model.',
      },
      {
        index: '04',
        title: 'Leave gaps as gaps.',
        body: 'Occluded, tiny, or unsupported checks stay not assessed.',
      },
      {
        index: '05',
        title: 'Hand over an honest record.',
        body: 'Supervisors and owners can see what was checked and what is still unknown. A later change to requirements does not rewrite that record.',
      },
    ],
  },
  scene: {
    eyebrow: 'On a site',
    title: 'One pass. Every hazard it looks for, and what is not one.',
    unavailable: 'This illustration could not start in this browser.',
    mark: 'Illustration',
    drive: 'Autonomous driving · in development',
    inset: 'Robot’s-eye view',
    twin: '2D Twin · planned',
    twinNote: 'Dots sit where the robot made each observation.',
    description:
      'Illustration of one inspection pass on a construction site. The rover marks a worker without safety glasses, a worker without a hard hat, a worker standing in its lane, a worker inside a taped restricted zone and pallets blocking a walkway as hazards. A worker half hidden by scaffolding is marked unverified. A fully equipped worker off the lane, and the barriers and materials, are marked no hazard.',
  },
  credits: {
    claim: 'Inspection that shows its work.',
    project: {
      text: 'A Knight Hacks project.',
      /** `label` must appear in `text`; that part becomes the link. */
      link: { label: 'Knight Hacks', href: 'https://2026.knighthacks.org/' },
    },
    /** `firstName` is what the cursor shows when hovering a name. */
    team: [
      { name: 'Maham Mehmood', firstName: 'Maham', linkedin: 'https://www.linkedin.com/in/mahammehmood/' },
      { name: 'Humberto Bohorquez', firstName: 'Humberto', linkedin: 'https://www.linkedin.com/in/humbertobohorquez/' },
      { name: 'Pablo Mendoza', firstName: 'Pablo', linkedin: 'https://www.linkedin.com/in/pablo-c-mendoza/' },
    ] as Array<{ name: string; firstName: string; role?: string; linkedin?: string }>,
    license:
      'Detections come from SH17 weights (CC BY-NC-SA 4.0) running on Ultralytics YOLOv8 (AGPL-3.0). Original project code is MIT licensed.',
  },
  dashboard: {
    eyebrow: 'Dashboard / Site manager',
    title: 'Inspection workspace.',
    sentence:
      'Validate site requirements, follow the camera’s observation trail, and review the evidence behind each finding.',
  },
} as const

export type SkillId = (typeof copy.skills.cards)[number]['id']
