/**
 * Validation error from FastAPI (HTTP 422)
 */
interface ValidationError {
  type: string
  loc: string[]
  msg: string
  input?: unknown
}

/**
 * Standard API error response
 */
export interface ApiError {
  status: number
  data: {
    detail: string | ValidationError[] | { detail: string; detail_code?: string }
    detail_code?: string
    errors?: Record<string, string[]>
  }
}

/**
 * Type guard to check if an error is an API error
 */
export function isApiError(error: unknown): error is ApiError {
  return (
    typeof error === 'object' &&
    error !== null &&
    'status' in error &&
    'data' in error
  )
}

/**
 * Extract error message from API error or unknown error with i18n support
 *
 * @param error - The error object from the API
 * @param t - Optional translation function from useTranslation hook
 * @returns Localized error message if translation function provided and code exists, otherwise fallback to English
 *
 * @example
 * ```tsx
 * const { t } = useTranslation(['backend'])
 * const errorMsg = getErrorMessage(error, t)
 * ```
 */
export function getErrorMessage(
  error: unknown,
  t?: (key: string) => string
): string {
  if (isApiError(error)) {
    const { detail } = error.data

    // Handle validation error array (HTTP 422)
    if (Array.isArray(detail)) {
      return detail.map(err => err.msg).join(', ')
    }

    // Handle detail object with detail_code
    if (typeof detail === 'object' && detail !== null && 'detail' in detail) {
      const detailObj = detail as { detail: string; detail_code?: string }

      // Try to use translation code if available
      if (t && detailObj.detail_code) {
        const translationKey = `backend:${detailObj.detail_code}`
        const translated = t(translationKey)
        // If translation exists and is different from key, use it
        if (translated && translated !== translationKey) {
          return translated
        }
      }

      // Fall back to English detail message
      return detailObj.detail || 'An error occurred'
    }

    // Handle legacy string detail
    if (typeof detail === 'string') {
      // Check for detail_code at top level
      if (t && error.data.detail_code) {
        const translationKey = `backend:${error.data.detail_code}`
        const translated = t(translationKey)
        if (translated && translated !== translationKey) {
          return translated
        }
      }
      return detail || 'An error occurred'
    }

    return 'An error occurred'
  }

  if (error instanceof Error) {
    return error.message
  }

  return 'An unexpected error occurred'
}

/**
 * Response with message and message_code for success responses
 */
export interface MessageResponse {
  message: string
  message_code: string
  [key: string]: unknown
}

/**
 * Extract success message from API response with i18n support
 *
 * @param response - The response object from the API
 * @param t - Optional translation function from useTranslation hook
 * @returns Localized success message if translation function provided and code exists, otherwise fallback to English
 *
 * @example
 * ```tsx
 * const { t } = useTranslation(['backend'])
 * const successMsg = getSuccessMessage(response, t)
 * toast.success(successMsg)
 * ```
 */
export function getSuccessMessage(
  response: MessageResponse | undefined | null,
  t?: (key: string) => string
): string {
  if (!response) {
    return 'Success'
  }

  // Try to use translation code if available
  if (t && response.message_code) {
    const translationKey = `backend:${response.message_code}`
    const translated = t(translationKey)
    // If translation exists and is different from key, use it
    if (translated && translated !== translationKey) {
      return translated
    }
  }

  // Fall back to English message
  return response.message || 'Success'
}
