import { getErrorMessage, isApiError } from '@/types/api'

/**
 * Server error as shown next to a form: the translated `detail_code` message
 * plus, when the backend sent one, its English detail (which names the
 * offending setting, e.g. "reset_pct must be below trigger_pct").
 */
export function getServerError(
  error: unknown,
  t: (key: string) => string
): { message: string; detail: string | null } {
  const message = getErrorMessage(error, t)
  let detail: string | null = null
  if (isApiError(error)) {
    const raw = error.data?.detail
    if (typeof raw === 'string') detail = raw
    else if (raw && !Array.isArray(raw) && typeof raw.detail === 'string') detail = raw.detail
  }
  return { message, detail: detail && detail !== message ? detail : null }
}

export function getErrorCode(error: unknown): string | null {
  if (!isApiError(error)) return null
  const raw = error.data?.detail
  if (raw && typeof raw === 'object' && !Array.isArray(raw) && 'detail_code' in raw) {
    return raw.detail_code ?? null
  }
  return error.data?.detail_code ?? null
}
