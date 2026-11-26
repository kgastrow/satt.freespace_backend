/**
 * URL validation utilities to prevent open redirect vulnerabilities.
 *
 * Open redirects occur when an application accepts user-controlled URLs
 * and redirects to them without validation, allowing attackers to redirect
 * users to malicious sites while appearing to come from a trusted domain.
 */

/**
 * Allowed internal paths for redirects after authentication.
 * Add new paths here as needed, but keep the list minimal.
 */
const ALLOWED_REDIRECT_PATHS = [
  '/dashboard',
  '/settings',
  '/admin',
  '/profile',
  '/files',
  '/notifications',
  '/help',
]

/**
 * Validates that a redirect path is safe (same-origin, internal path).
 *
 * @param path - The path to validate
 * @returns true if the path is safe for redirect, false otherwise
 *
 * Security checks:
 * - Must be a string
 * - Must start with '/' (relative path)
 * - Must not start with '//' (protocol-relative URL)
 * - Must not contain protocol (http:, https:, javascript:, etc.)
 * - Must not contain URL encoding that could bypass checks
 */
export function isValidRedirectPath(path: unknown): path is string {
  if (typeof path !== 'string') {
    return false
  }

  // Must be a relative path starting with /
  if (!path.startsWith('/')) {
    return false
  }

  // Block protocol-relative URLs (//evil.com)
  if (path.startsWith('//')) {
    return false
  }

  // Block URLs with protocols
  if (/^\/[a-z]+:/i.test(path)) {
    return false
  }

  // Block encoded characters that could bypass checks
  // %2f = /, %5c = \, %00 = null byte
  const lowerPath = path.toLowerCase()
  if (lowerPath.includes('%2f') || lowerPath.includes('%5c') || lowerPath.includes('%00')) {
    return false
  }

  // Block backslashes (can be interpreted as forward slashes in some browsers)
  if (path.includes('\\')) {
    return false
  }

  return true
}

/**
 * Gets a safe redirect path, falling back to default if the provided path is invalid.
 *
 * @param path - The requested redirect path (may be user-controlled)
 * @param defaultPath - The default path to use if validation fails (default: '/dashboard')
 * @returns A validated safe path
 */
export function getSafeRedirectPath(path: unknown, defaultPath = '/dashboard'): string {
  if (isValidRedirectPath(path)) {
    return path
  }
  return defaultPath
}

/**
 * Checks if a path starts with any of the allowed redirect prefixes.
 * Use this for stricter validation when you want to limit redirects to specific sections.
 *
 * @param path - The path to validate
 * @returns true if the path is in the allowed list, false otherwise
 */
export function isAllowedRedirectPath(path: unknown): boolean {
  if (!isValidRedirectPath(path)) {
    return false
  }

  // Check if path starts with any allowed prefix
  return ALLOWED_REDIRECT_PATHS.some(
    (allowed) => path === allowed || path.startsWith(`${allowed}/`)
  )
}

/**
 * Allowed domains for external download URLs (e.g., S3 buckets).
 * Configure this based on your infrastructure.
 * Patterns support wildcards: *.s3.amazonaws.com matches any S3 bucket.
 */
const ALLOWED_DOWNLOAD_DOMAINS = [
  // AWS S3 patterns
  '*.s3.amazonaws.com',
  '*.s3.*.amazonaws.com',
  's3.amazonaws.com',
  's3.*.amazonaws.com',
  // Add other cloud storage domains as needed
  // '*.storage.googleapis.com',
  // '*.blob.core.windows.net',
]

/**
 * Validates that a download URL is safe to open.
 *
 * SEC-F-011: Prevents opening malicious URLs that could be injected via
 * compromised API responses.
 *
 * @param url - The download URL to validate
 * @returns true if the URL is safe to open, false otherwise
 *
 * Security checks:
 * - Must be a valid URL
 * - Must be HTTPS (or same-origin for relative URLs)
 * - Must be from same origin OR an allowed external domain
 * - Must not contain javascript: or data: protocols
 */
export function isValidDownloadUrl(url: unknown): url is string {
  if (typeof url !== 'string' || url.length === 0) {
    return false
  }

  // Allow relative URLs (same-origin)
  if (url.startsWith('/') && !url.startsWith('//')) {
    return isValidRedirectPath(url)
  }

  // Block dangerous protocols
  const lowerUrl = url.toLowerCase().trim()
  if (
    lowerUrl.startsWith('javascript:') ||
    lowerUrl.startsWith('data:') ||
    lowerUrl.startsWith('vbscript:')
  ) {
    return false
  }

  // Parse the URL
  let parsedUrl: URL
  try {
    parsedUrl = new URL(url)
  } catch {
    return false
  }

  // Must be HTTPS for external URLs
  if (parsedUrl.protocol !== 'https:') {
    // Allow HTTP only for localhost in development
    if (
      parsedUrl.protocol === 'http:' &&
      (parsedUrl.hostname === 'localhost' || parsedUrl.hostname === '127.0.0.1')
    ) {
      return true
    }
    return false
  }

  // Check if same origin
  if (parsedUrl.origin === window.location.origin) {
    return true
  }

  // Check against allowed external domains
  const hostname = parsedUrl.hostname.toLowerCase()
  return ALLOWED_DOWNLOAD_DOMAINS.some((pattern) => {
    if (pattern.startsWith('*.')) {
      // Wildcard pattern: *.s3.amazonaws.com
      const suffix = pattern.slice(1) // .s3.amazonaws.com
      return hostname.endsWith(suffix) || hostname === pattern.slice(2)
    }
    return hostname === pattern
  })
}

/**
 * Safely opens a download URL in a new tab/window.
 *
 * SEC-F-011: Validates the URL before opening to prevent open redirect attacks
 * from compromised API responses.
 *
 * @param url - The download URL to open
 * @param fallbackMessage - Optional message to show if URL is invalid
 * @returns true if URL was opened, false if validation failed
 */
export function safeOpenDownloadUrl(
  url: string,
  fallbackMessage = 'Invalid download URL'
): boolean {
  if (!isValidDownloadUrl(url)) {
    console.warn(`Blocked invalid download URL: ${url}`)
    // Optionally show user feedback
    if (typeof window !== 'undefined' && fallbackMessage) {
      // Don't alert - let caller handle the error
    }
    return false
  }

  window.open(url, '_blank', 'noopener,noreferrer')
  return true
}
