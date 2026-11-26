/**
 * Lightweight breadcrumb trail used to enrich error reports with the user's
 * recent activity ("what action triggered this"). Keeps an in-memory ring
 * buffer of the last few navigation + click events. Only UI labels are
 * captured (button text, aria-label, link text) — never input values — so no
 * sensitive data is recorded.
 */

export type BreadcrumbType = 'navigation' | 'click'

export interface Breadcrumb {
  type: BreadcrumbType
  label: string
  timestamp: string
}

const MAX_BREADCRUMBS = 15
const MAX_LABEL_LENGTH = 100

const buffer: Breadcrumb[] = []

/** Append a breadcrumb, evicting the oldest once the buffer is full. */
export function recordBreadcrumb(type: BreadcrumbType, label: string): void {
  const trimmed = label.trim().replace(/\s+/g, ' ')
  if (!trimmed) return

  buffer.push({
    type,
    label: trimmed.slice(0, MAX_LABEL_LENGTH),
    timestamp: new Date().toISOString(),
  })

  if (buffer.length > MAX_BREADCRUMBS) {
    buffer.shift()
  }
}

/** Snapshot of the current breadcrumb trail (oldest first). */
export function getBreadcrumbs(): Breadcrumb[] {
  return [...buffer]
}

let installed = false

/**
 * Install global listeners that record click breadcrumbs. Idempotent and safe
 * to call on every mount; navigation breadcrumbs are recorded separately by the
 * router-aware caller.
 */
export function installBreadcrumbCollectors(): void {
  if (installed || typeof window === 'undefined') return
  installed = true
  window.addEventListener('click', handleClick, { capture: true })
}

function handleClick(event: MouseEvent): void {
  const target = event.target as HTMLElement | null
  const el = target?.closest<HTMLElement>(
    'button, a, [role="button"], [data-breadcrumb]',
  )
  if (!el) return

  const label = getInteractiveLabel(el)
  if (label) {
    recordBreadcrumb('click', `Clicked "${label}"`)
  }
}

function getInteractiveLabel(el: HTMLElement): string {
  return (
    el.getAttribute('data-breadcrumb') ||
    el.getAttribute('aria-label') ||
    el.textContent?.trim() ||
    el.getAttribute('title') ||
    ''
  )
}
