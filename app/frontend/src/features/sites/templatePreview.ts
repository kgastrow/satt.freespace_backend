import type { AdvisoryType } from '@/types/site'

/** Same grammar as the backend (services/freespace/templates.py). */
const PLACEHOLDER_RE = /\{([A-Za-z][A-Za-z0-9_]*)\}/g

export const MAX_TITLE_LENGTH = 255
export const MAX_BODY_LENGTH = 2000

export const ADVISORY_TYPES: readonly AdvisoryType[] = [
  'SITE_INITIAL',
  'SITE_CHANGE',
  'ZONE_ADVISORY',
  'RECOVERY',
  'TEST',
]

/** Names of the placeholders used in `text`, in order of first appearance. */
export function extractPlaceholders(text: string): string[] {
  const found: string[] = []
  for (const match of text.matchAll(PLACEHOLDER_RE)) {
    if (!found.includes(match[1])) found.push(match[1])
  }
  return found
}

/** Placeholders in `text` that the type does not provide (BF-70). */
export function findUnknownPlaceholders(text: string, allowed: readonly string[]): string[] {
  return extractPlaceholders(text).filter((name) => !allowed.includes(name))
}

export type PlaceholderSamples = Record<string, string>

/** Sample values for the live preview; `{site}` uses the real site name. */
export function sampleValues(siteName: string): PlaceholderSamples {
  return {
    site: siteName,
    zone: 'Basement 3',
    topZones: 'Basement 3 and Basement 4',
    occupancyPct: '92',
    fullZone: 'Basement 1',
  }
}

/**
 * Substitute sample values. Placeholders without a sample (or not allowed for
 * the type) are left as written, so a typo stays visible in the preview.
 */
export function renderPreview(
  text: string,
  samples: PlaceholderSamples,
  allowed?: readonly string[]
): string {
  return text.replace(PLACEHOLDER_RE, (whole, name: string) => {
    if (allowed && !allowed.includes(name)) return whole
    return Object.prototype.hasOwnProperty.call(samples, name) ? samples[name] : whole
  })
}

/** Insert `{name}` at the selection and report where the cursor should go. */
export function insertPlaceholder(
  text: string,
  selectionStart: number,
  selectionEnd: number,
  name: string
): { text: string; cursor: number } {
  const token = `{${name}}`
  const start = Math.max(0, Math.min(selectionStart, text.length))
  const end = Math.max(start, Math.min(selectionEnd, text.length))
  return { text: text.slice(0, start) + token + text.slice(end), cursor: start + token.length }
}

export function isTemplateChanged(
  current: { title: string; body: string },
  saved: { title: string; body: string }
): boolean {
  return current.title !== saved.title || current.body !== saved.body
}
