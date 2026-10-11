export const workerPolicy = {
  title: 'Worker privacy & safety.',
  updated: 'October 11, 2026',
  updatedDate: '2026-10-11',
  introduction:
    'B.O.B supports a site manager’s review of PPE and restricted zones. This policy limits how worker images may be collected, used and kept, and keeps decisions about people with a human reviewer.',
  summary: [
    { value: '7 days', label: 'Routine images · maximum from capture' },
    { value: '30 days', label: 'Incident evidence · maximum from capture' },
    { value: 'Human review', label: 'Every finding that affects a worker' },
  ],
  retention: [
    {
      category: 'Routine images',
      period: '7 days',
      instruction: 'Delete sooner when no longer needed. Includes saved previews and images not retained for an incident review.',
    },
    {
      category: 'Incident evidence',
      period: '30 days',
      instruction: 'Keep only frames needed to review a reported incident. Delete sooner when the review is complete and no further retention is necessary.',
    },
    {
      category: 'Documented hold',
      period: 'Reviewed weekly',
      instruction: 'A legally required hold or active investigation may extend retention for relevant images only. Record the reason, responsible person and next review date; delete when the hold ends.',
    },
  ],
  retentionNote:
    'Periods run from the original capture time. Copying an image or reclassifying a finding does not restart its clock. Apply the same limits to rover and laptop copies, recordings, exports, backups and linked metadata that can identify a worker.',
  implementation:
    'Deletion is operator-managed in the current prototype. Automatic expiry across all devices and copies is not implemented. Rover storage cleanup does not remove laptop copies, saved previews or recordings. The site operator must arrange and verify deletion against this schedule before using B.O.B with workers.',
  sections: [
    {
      id: 'collection',
      title: 'Collect only what the inspection needs.',
      paragraphs: [
        'Inspection data can include camera images, visible people and PPE, model confidence, timestamps, session details and the camera’s observation position. Faces and bystanders may appear in a frame. B.O.B does not use facial recognition to identify workers.',
        'The site operator must explain the inspection areas, purpose, retention periods and privacy contact to workers and visitors before capture. Keep cameras out of toilets, changing rooms and other private spaces. Limit capture to the inspection area and avoid unnecessary bystander images.',
      ],
    },
    {
      id: 'access',
      title: 'Keep worker images within the review.',
      paragraphs: [
        'Only authorized site managers and safety reviewers may access inspection images for the stated purpose. The current pipeline stores images on the rover computer and operator laptop. Protect those devices, their access credentials and any exported copies; use protected network connections.',
        'Do not sell images or use them for advertising, productivity rankings, identity tracking or model training. Share only the minimum evidence needed with an authorized recipient, and record the recipient and reason. Public website photographs require separate permission or an appropriate license and must never be drawn from live worker inspections.',
      ],
    },
    {
      id: 'safety',
      title: 'A finding needs a person’s judgment.',
      paragraphs: [
        'The site manager selects PPE checks based on the worksite’s actual requirements. Review the original frame and context with the worker before making a decision. A model’s confidence is a detection score, not a measure of compliance or worker safety. Unclear, occluded or unsupported checks remain unverified.',
        'Do not use an automated finding alone for discipline or employment decisions. B.O.B supports inspection; it does not replace hazard assessments, training, required PPE, qualified supervision or emergency procedures. Do not rely on detections or camera position for collision avoidance, stopping the rover or declaring an area safe.',
      ],
    },
    {
      id: 'requests',
      title: 'Workers can ask and challenge.',
      paragraphs: [
        'Ask the site manager or the privacy contact named in the site notice to explain a finding, review an image involving you, correct the record or request deletion. Give the approximate inspection date, time and area so the operator can locate the relevant material without collecting unnecessary identity details.',
        'The site operator must review requests, protect other people shown in the same frame, explain any documented reason for retaining evidence and record the outcome. Raise immediate hazards through the site’s normal safety or emergency process. Privacy concerns must be heard without retaliation.',
      ],
    },
  ],
  responsibility:
    'The organization operating B.O.B is responsible for worker notice, permitted use, access and deletion. It must name a contact in its site notice and check applicable privacy and workplace requirements before deployment. These retention periods are this site policy’s limits, not a claim that every jurisdiction requires the same periods.',
  sources: [
    {
      label: 'ICO · surveillance, transparency and retention guidance',
      href: 'https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/cctv-and-video-surveillance/guidance-on-video-surveillance-including-cctv/how-can-we-comply-with-the-data-protection-principles-when-using-surveillance-systems/',
    },
    {
      label: 'OSHA · employer responsibilities',
      href: 'https://www.osha.gov/workers/employer-responsibilities',
    },
  ],
} as const
