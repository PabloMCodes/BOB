/**
 * Current status updates — the honest state of the build.
 *
 * `working` is demonstrated end to end. `wired` is physically connected but the
 * code or the test is still missing. `planned` is not started. Keep anything
 * unmeasured as `null` so the page prints "TBD" instead of inventing a number.
 */

export type StatusLevel = 'working' | 'wired' | 'partial' | 'planned'

export const statusLevelLabel: Record<StatusLevel, string> = {
  working: 'Working',
  wired: 'Wired · untested',
  partial: 'Partly working',
  planned: 'Planned',
}

/** Fill in once the obstruction-detection run is measured, e.g. '71%'. */
export const obstructionConfidence: string | null = null

export const metricPending = 'TBD'

export type StatusMetric = { label: string; value: string | null }

export type StatusItem = {
  title: string
  body: string
  metrics?: StatusMetric[]
}

export type StatusGroup = {
  level: StatusLevel
  title: string
  note: string
  items: StatusItem[]
}

/** A photograph of the actual build. Files live in public/media/status. */
export type StatusPhoto = {
  src: string
  alt: string
  caption: string
}

export type StatusSection = {
  id: string
  eyebrow: string
  title: string
  summary: string
  components: Array<{ name: string; note: string }>
  photos?: StatusPhoto[]
  groups: StatusGroup[]
}

export const statusPage = {
  eyebrow: 'Current status updates',
  title: 'Where the build actually stands.',
  sentence:
    'A running account of what is working on the robot today, what is wired but not yet finished, and what comes next. Hardware and software are tracked separately, because one being ready does not make the other ready.',
  updated: 'Updated continuously as the prototype changes.',
  heroPhoto: {
    src: '/media/status/status-hero-driving.jpg',
    alt: 'A team member crouched on the floor beside the B.O.B prototype, driving it from a phone.',
    caption: 'The prototype on the floor, driven by hand. Every pass today is a driven pass.',
  } as StatusPhoto,
  sections: [
    {
      id: 'hardware',
      eyebrow: 'Hardware',
      title: 'The robot itself.',
      summary:
        'B.O.B runs on an NVIDIA Jetson Orin Nano for all on-board compute, with an ESP32 microcontroller as the bridge between that compute and the physical world. The ESP32 drives the motors over PWM and carries the sensor lines; an iPhone on the mast supplies the camera and pose; an on-board speaker announces out loud that PPE is missing the moment a person is seen without it. A hazardous gas sensor, a radar module and wheel encoders for navigation are mounted and wired alongside them. The hazard and object detection the robot runs on board is heavily OpenCV-based, working frame by frame on what the mast camera sees.',
      components: [
        { name: 'NVIDIA Jetson Orin Nano', note: 'On-board compute. Vision and logging run here, with no connection required.' },
        { name: 'ESP32', note: 'Microcontroller bridge: PWM motor control and the sensor lines back to the Jetson.' },
        { name: 'iPhone on the mast', note: 'Camera frames, timestamps and ARKit pose, streamed to the Jetson.' },
        { name: 'PWM drive motors', note: 'Forward, reverse and turning, commanded through the ESP32.' },
        { name: 'Speaker', note: 'Announces missing PPE out loud, so the worker hears it on the spot rather than reading it later.' },
        { name: 'Hazardous gas sensor', note: 'Air-quality sensing for pre-shift inspection. Mounted and wired.' },
        { name: 'Radar module', note: 'Non-camera sensing for dust, when the phone camera is obscured. Mounted and wired.' },
        { name: 'Wheel encoders', note: 'Distance and turn feedback for navigation. Mounted and wired.' },
      ],
      photos: [
        {
          src: '/media/status/hardware-rover-bench.jpg',
          alt: 'The B.O.B chassis on a bench: breadboard, ESP32, battery pack and the Jetson Orin Nano beside it, with the power converter wired between them.',
          caption:
            'The ESP32 connections on the chassis, and the wired connections from the power converter and the Jetson Orin Nano into the ESP32.',
        },
      ],
      groups: [
        {
          level: 'working',
          title: 'Functional and working',
          note: 'Built, connected and demonstrated on the prototype.',
          items: [
            {
              title: 'Working speaker for missing-PPE announcements.',
              body: 'The audio path works end to end: when a person is detected without a required item, the robot announces out loud through its speaker that the PPE is missing, rather than leaving the finding in a log for later.',
            },
            {
              title: 'Full drive and turning under PWM motor control.',
              body: 'The rover drives forward and in reverse and turns under its own power, with motor speed and direction commanded through PWM.',
            },
            {
              title: 'ESP32 fully wired to the Jetson.',
              body: 'The microcontroller is completely wired and communicating with the Jetson Orin Nano, which is the link every motor command and sensor reading depends on.',
            },
          ],
        },
        {
          level: 'wired',
          title: 'Wired, with coding and testing outstanding',
          note: 'Physically connected. The firmware, the integration or the test has not been completed, so neither is claimed as working.',
          items: [
            {
              title: 'Hazardous gas sensor.',
              body: 'Mounted and wired to the ESP32. Reading, thresholds and reporting are not finished, and the sensor has not been tested against a known source.',
            },
            {
              title: 'Radar, for seeing through dust.',
              body: 'Intended for the case the phone camera cannot handle: dust, or a lens that has been covered over. Wired in place, with the sensing code and validation still ahead of us.',
            },
            {
              title: 'Encoders, for navigation.',
              body: 'Wheel encoders are wired to the ESP32 to give the robot how far it has travelled and how far it has turned — the feedback autonomous navigation will be built on. They have not been read or tested yet, so no distance or heading from them is trusted today.',
            },
          ],
        },
      ],
    },
    {
      id: 'software',
      eyebrow: 'Software',
      title: 'What the robot understands.',
      summary:
        'Vision runs as YOLOv8 on SH17 weights, further trained by us on data we labelled ourselves in Roboflow, which is what produces the per-person PPE checks. When a check comes back missing, the robot says so out loud through its speaker. Obstruction detection runs through the Gemini API. Taped-off restricted areas are recognized by YOLO. Drive commands are issued from the operator computer today.',
      components: [
        { name: 'YOLOv8 + SH17 weights', note: 'Person and PPE detection, trained further on our own Roboflow-labelled data.' },
        { name: 'Our Roboflow training set', note: 'Labelled by the team, not taken off the shelf. It is what lifted the PPE classes.' },
        { name: 'Gemini API', note: 'Obstruction detection on the captured frame.' },
        { name: 'YOLO zone detection', note: 'Taped-off restricted areas recognized from floor tape.' },
        { name: 'Operator drive control', note: 'Driving commanded from the computer over the local link.' },
      ],
      photos: [
        {
          src: '/media/status/software-live-ppe-glasses-detected.jpg',
          alt: 'The live stream window with a person boxed and labelled no-helmet, no-safety-vest and no-gloves, the eyewear boxed, and the glasses verdict reading wearing.',
          caption:
            'The tracking software running live: person, PPE and pose tracked on every frame, with the stream header carrying frame rate, drops, added latency and pose validity alongside the per-item verdicts.',
        },
      ],
      groups: [
        {
          level: 'working',
          title: 'Functional and working',
          note: 'Running on real frames, with measured confidence where we have measured it.',
          items: [
            {
              title: 'Camera and PPE detection.',
              body: 'The camera path works completely, and the model determines whether a person is wearing the correct PPE, with the robot announcing out loud whenever a required item is missing. It is YOLO on SH17 weights with our own Roboflow training on top. The large, high-contrast items are the strongest: safety glasses and high-visibility vests both clear 60% confidence, while the smaller items — gloves and boots — sit around 30% and are the clearest target for further training.',
              metrics: [
                { label: 'Safety glasses', value: 'Over 60%' },
                { label: 'High-visibility vest', value: 'Over 60%' },
                { label: 'Gloves', value: '~30%' },
                { label: 'Safety boots', value: '~30%' },
              ],
            },
            {
              title: 'Obstruction detection through the Gemini API.',
              body: 'Fully working: blocked walkways and obstacles in the path are identified on the frame, which is the core of the pre-shift pass.',
              metrics: [{ label: 'Obstruction confidence', value: obstructionConfidence }],
            },
            {
              title: 'Taped-off area detection.',
              body: 'YOLO recognizes floor tape marking a restricted zone, so a person standing inside one becomes a finding rather than a judgement call.',
            },
          ],
        },
        {
          level: 'partial',
          title: 'Working, but not yet autonomous',
          note: 'Demonstrated under an operator. The autonomous version is not built.',
          items: [
            {
              title: 'Driving is controlled locally, not autonomously.',
              body: 'The rover can be driven from the computer over the local link, and that works reliably. It does not yet plan or choose its own route, so every pass today is a driven pass.',
            },
          ],
        },
      ],
    },
  ] as StatusSection[],
  next: {
    eyebrow: 'What’s next',
    title: 'The work we are heading into.',
    items: [
      {
        index: '01',
        title: 'Finish non-camera vision for dusty environments.',
        body: 'Complete the radar wiring and the sensing code behind it, so a covered or dust-blinded camera no longer means a blind robot.',
      },
      {
        index: '02',
        title: 'Widen pre-shift inspection.',
        body: 'Bring more of the pre-shift checklist on board, starting with the air-quality sensing the gas sensor is already wired for.',
      },
      {
        index: '03',
        title: 'Fully autonomous agentic driving.',
        body: 'Move from a driven pass to a robot that runs the route itself and decides where a closer look is warranted.',
      },
      {
        index: '04',
        title: 'A design built for the conditions.',
        body: 'Adapt the chassis to a real site, the caster wheel first — rubble and uneven slab are what the current prototype struggles with.',
      },
      {
        index: '05',
        title: 'Raise model confidence through more training.',
        body: 'Keep labelling and training to lift the weaker classes, with gloves and boots at roughly 30% the first priority.',
      },
    ],
  },
} as const
