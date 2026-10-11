import { workerPolicy } from './privacy.ts'

export const serviceTerms = {
  title: 'Terms of Service.',
  organization: 'Building-site Observation Bot .INC',
  contactEmail: 'thisisnotarealemail67@knighthacks.com',
  updated: 'October 11, 2026',
  updatedDate: '2026-10-11',
  introduction:
    'These terms cover the B.O.B website and inspection prototype. Read them together with the worker privacy and safety policy before connecting a worksite or collecting images.',
  sections: [
    {
      id: 'scope',
      title: '1. Scope and authorized use',
      paragraphs: [
        'Building-site Observation Bot .INC offers B.O.B as an inspection prototype. Use the website and connected tools only when you can follow these terms. If you do not agree, stop using the service. If you operate B.O.B for an organization, you must have its authority to manage the installation and the worksite data.',
        'A locally deployed installation remains under its site operator’s control. The operator manages access, devices, worker notice and inspection records. These service terms do not replace or restrict rights granted by the project’s open-source licenses.',
      ],
    },
    {
      id: 'acceptable-use',
      title: '2. Acceptable use',
      paragraphs: [
        'Use B.O.B for authorized inspection, research or evaluation consistent with the licenses of the components you use. Capture only areas you are permitted to inspect. Do not use the service for covert monitoring, harassment, identity tracking or productivity ranking.',
        'Do not bypass access controls, disclose other people’s credentials, disrupt an installation operated by someone else, submit malicious material or falsify inspection evidence. Do not publish worker images or use them for advertising or model training without separate, appropriate authorization.',
      ],
    },
    {
      id: 'worker-safety',
      title: '3. Human review and worker safety',
      paragraphs: [
        'The site manager must set PPE requirements according to the actual worksite and review the original frame, its context and the worker’s explanation before taking action. Saved requirements apply to the next explicitly started inspection. “Not required” excludes a check; it does not establish compliance. Missing, uncertain or unsupported observations remain unverified.',
        'A confidence score is a model detection score. Do not use an automated finding alone for discipline or an employment decision. B.O.B does not replace hazard assessment, required PPE, training, qualified supervision or emergency procedures. Do not use detections or camera position as a collision-avoidance or emergency-stop system, or as proof that a worker or area is safe.',
      ],
    },
    {
      id: 'worker-data',
      title: '4. Worker images and inspection data',
      paragraphs: [
        'You must have an appropriate basis and authority to capture, process and share inspection data, inform workers and visitors, protect access, and address requests to review, correct or delete records. The site operator is responsible for its installation and every copy it creates or shares.',
        `Follow the worker privacy and safety policy: routine images have a maximum retention of ${workerPolicy.retention[0].period} from capture, and incident evidence has ${workerPolicy.retention[1].period}, subject to documented holds. Deletion is operator-managed. Automatic expiry across all devices, recordings, exports and backups is not implemented. Ending an inspection or disconnecting the dashboard does not erase stored images.`,
        'These terms give Building-site Observation Bot .INC no permission to sell, publicly display or train models on your inspection images. Sharing evidence with an authorized recipient must be limited to the stated inspection purpose and follow the privacy policy.',
      ],
    },
    {
      id: 'access-availability',
      title: '5. Access, availability and ending use',
      paragraphs: [
        'Keep hub credentials private, use protected devices and network connections, and give access only to authorized reviewers. SAMPLE data is demonstration material and must not be represented as a live inspection. Connection failures, stale data and missing evidence must remain visible when interpreting a record.',
        'The prototype may change, be interrupted or become unavailable. No uptime, support response time or evidence-recovery service is promised. An operator may revoke access to its installation for misuse or a security concern. You may stop using B.O.B at any time; the operator must still handle retained data and outstanding worker requests under the privacy policy.',
        'The current website has no subscription checkout or payment processing. Any future paid service would require separately disclosed pricing and terms and your explicit authorization.',
      ],
    },
    {
      id: 'licenses',
      title: '6. Software, models and other materials',
      paragraphs: [
        'Original B.O.B source code and documentation are licensed under the MIT License, copyright 2026 BOB contributors. Third-party code, weights, datasets and photographs keep their own licenses and permissions. These terms do not relicense them or reduce permissions granted by their applicable licenses.',
        'The current SH17-based weights are documented as non-commercial, with CC BY-NC-SA 4.0 provenance. Ultralytics is licensed under AGPL-3.0. Review each model card and its upstream terms before distributing a combined application or considering commercial use; the MIT license for original project code does not remove those separate obligations.',
      ],
    },
    {
      id: 'warranties',
      title: '7. Prototype limitations and liability',
      paragraphs: [
        'To the extent permitted by applicable law, the website and prototype are provided as available, without warranties of accuracy, completeness, uninterrupted operation or fitness for a particular purpose. Detections can be wrong or incomplete, and records may be unavailable. B.O.B does not guarantee injury prevention or regulatory compliance.',
        'To the extent permitted by applicable law, Building-site Observation Bot .INC is not liable for indirect or consequential losses arising from use of the website or prototype. Nothing in these terms excludes liability or statutory rights that cannot lawfully be excluded, or removes an employer’s duties to workers. Separate software licenses contain their own warranty and liability provisions.',
      ],
    },
    {
      id: 'updates',
      title: '8. Updates and questions',
      paragraphs: [
        'Revisions will be posted on this page with a new version or updated date. Material changes should be brought to the attention of operators before they take effect. A revision does not grant new uses of previously collected worker images or restart their retention periods.',
        'For service questions, contact Building-site Observation Bot .INC using the email below. For access to a particular worker image, a correction or a deletion request, contact the site manager or privacy contact named in that worksite’s notice. Immediate hazards must go through the site’s normal safety or emergency process.',
      ],
    },
  ],
  references: [
    { label: 'Original B.O.B source license', href: 'https://github.com/PabloMCodes/BOB/blob/main/LICENSE' },
    { label: 'CC BY-NC-SA 4.0', href: 'https://creativecommons.org/licenses/by-nc-sa/4.0/' },
    { label: 'Ultralytics licensing', href: 'https://www.ultralytics.com/license' },
    { label: 'OSHA · employer responsibilities', href: 'https://www.osha.gov/workers/employer-responsibilities' },
  ],
} as const
