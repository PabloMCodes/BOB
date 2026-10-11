/** Photographs and clips for the homepage. Files go in public/media; leave an entry out until its file exists. */

import type { SkillId } from './copy.ts'

/** Box edges are fractions of the original image, origin at the top left. */
export type LookBox = {
  label: string
  x: number
  y: number
  w: number
  h: number
}

export type Media = {
  /** Path under public/, e.g. '/media/skills/ppe.jpg'. */
  src: string
  kind: 'image' | 'video'
  alt: string
  /** Focal point when an image is cropped to fill its card. */
  objectPosition?: string
  /** Only for clean images. Leave empty when the boxes are drawn into the file. */
  boxes?: LookBox[]
}

/**
 * Hero background. To use an image, put it in public/media/hero/ and replace `null`, e.g.
 * { src: '/media/hero/rover-on-site.jpg', kind: 'image', alt: 'B.O.B on a construction site' }
 */
export const heroBackground: Media | null = null

export const skillMedia: Partial<Record<SkillId, Media>> = {
  ppe: {
    src: '/media/workers/03-site-dusk-hivis-detections.jpg',
    kind: 'image',
    alt: 'Two workers in hard hats and high-visibility jackets, with person, helmet, eyewear and vest detection labels.',
    objectPosition: '85% center',
  },
}
