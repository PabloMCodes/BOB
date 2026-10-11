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
    /** Nav labels sit on one row — keep this short; the page itself is titled in full. */
    status: 'Status',
    inspiration: 'Inspiration',
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
  why: {
    eyebrow: 'Why B.O.B',
    title: 'The sites that most need watching are the hardest ones to reach.',
    lead: 'Almost every AI safety inspection system on the market assumes two things: a steady connection, and a forgiving environment. A construction site offers neither.',
    paragraphs: [
      'Dust, noise, half-finished floors and the dead zones between them are exactly where cloud-dependent monitoring stops being an option — and exactly where the hazards are.',
      'The few systems that do hold up offline are built for a different customer. A Spot unit walking a NextEra energy site is a remarkable machine, and a deliberately generalized one, priced for owners with a fleet, a budget line and a site large enough to justify both. For a smaller contractor, it was never a difficult decision. It was never a decision at all.',
      'One of us, Pablo, has a father who works in construction. Talking with him made the gap concrete. The hazards that matter most are the ordinary, repeating ones, and PPE sits at the top of that list. A shift leader answers for every worker on site at once, and nobody can look in every direction for an entire shift. The checks that slip are not the complicated ones — they are the constant ones.',
      'He confirmed the other constraint too, the one we had already run into: whatever watches a site has to keep working when the connection does not.',
    ],
  },
  targets: {
    eyebrow: 'What we aim to target',
    title: 'Three gaps to close, to make construction robots accessible.',
    items: [
      {
        index: '01',
        title: 'AI safety and inspection where there is no connectivity.',
        body: 'B.O.B logs continuously on the Jetson it carries — findings, frames and timestamps held on the robot itself. The moment a connection returns, the photographs and the full record are delivered straight to the shift supervisor, with nothing lost to the gap.',
      },
      {
        index: '02',
        title: 'Lower cost, because the cost is measured in lives.',
        body: 'B.O.B is built around the NVIDIA Jetson Orin Nano dev kit, the most affordable supercomputer available. Our prototype came to under $900 in total — every piece of hardware and software, Jetson included. Against generalized offline inspection platforms such as Spot, which are built for far larger customers and far larger sites, that is roughly a 99.5% reduction. At that price, meaningful safety monitoring comes within reach of the companies that could never before consider it.',
      },
      {
        index: '03',
        title: 'Covering the gaps a person cannot.',
        body: 'A second set of eyes on the crew, because a shift supervisor cannot be everywhere at once. And for the conditions no visual check can catch, a hazardous-gas sensing payload is next on the roadmap — inspection for places it is not safe to send someone to look.',
      },
    ],
  },
  overview: {
    eyebrow: 'What it is',
    statement:
      'An iPhone on the mast streams what B.O.B sees to the computer it carries. Vision models find people and the gear on them, check only what that worksite requires, and keep every finding with the frame it came from. Nothing unseen is reported as safe.',
    rolesLead: 'B.O.B does two jobs on a site, and the shift is what separates them.',
    roles: [
      {
        label: 'Before the shift',
        title: 'A pre-shift inspection robot.',
        body: 'It walks the site ahead of the crew, finding obstacles and obstructions in the walkways and recognizing the taped-off areas that are meant to stay empty — so the hazards are on record before anyone is standing next to them.',
      },
      {
        label: 'During the shift',
        title: 'A supervisor’s sidekick.',
        body: 'Once the crew is working, it keeps watching how PPE is actually being worn, person by person, and speaks up on the spot. It is the second set of eyes a shift supervisor cannot be.',
      },
    ],
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
        body: 'A closed yellow floor outline is recognized, and feet inside it become a finding. Anything less stays unverified.',
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
    /**
     * Stock photographs the skills cards run on. Both are share-alike, so the annotated versions
     * carry the same licence as the photograph they are derived from. Full provenance and what
     * each detector run returned: public/media/skills/sources.json.
     */
    photos: [
      {
        title: 'Construction on Erwin Rd in Durham',
        author: 'Ildar Sagdejev (Specious)',
        href: 'https://commons.wikimedia.org/wiki/File:2008-07-15_Construction_on_Erwin_Rd_in_Durham.jpg',
        license: 'CC BY-SA 4.0',
        licenseHref: 'https://creativecommons.org/licenses/by-sa/4.0/',
      },
      {
        title: '5S Door-range line',
        author: 'Adrian Grycuk',
        href: 'https://commons.wikimedia.org/wiki/File:5S_Door-range_line.jpg',
        license: 'CC BY-SA 3.0 PL',
        licenseHref: 'https://creativecommons.org/licenses/by-sa/3.0/pl/deed.en',
      },
    ],
  },
  dashboard: {
    eyebrow: 'Dashboard / Site manager',
    title: 'Inspection workspace.',
    sentence:
      'Validate site requirements, follow the camera’s observation trail, and review the evidence behind each finding.',
  },
} as const

export type SkillId = (typeof copy.skills.cards)[number]['id']
