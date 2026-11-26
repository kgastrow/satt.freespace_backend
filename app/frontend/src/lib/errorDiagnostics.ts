/**
 * Builds a structured diagnostics payload from a caught React error. This is
 * what gets attached (as JSON) to a support item so support can see the page,
 * component, recent actions and environment without asking the user.
 */

import { getBreadcrumbs, type Breadcrumb } from './errorBreadcrumbs'

export interface ErrorDiagnostics {
  error: {
    name: string
    message: string
    stack: string | null
  }
  page: {
    url: string
    pathname: string
  }
  /** Best-effort name of the component that threw (top of the component stack). */
  component: string | null
  componentStack: string | null
  breadcrumbs: Breadcrumb[]
  environment: {
    userAgent: string
    language: string
    screenResolution: string
    viewport: string
    appVersion: string
    commit: string
    timestamp: string
  }
}

const APP_VERSION = import.meta.env.VITE_BUILD_VERSION || '0.0.0'
const APP_COMMIT = import.meta.env.VITE_BUILD_COMMIT || 'development'

/**
 * Pull the first component name out of a React component stack. Frames look
 * like "\n    at ComponentName (...)" (React 19) or "\n    in ComponentName".
 */
export function extractComponentName(componentStack: string | null): string | null {
  if (!componentStack) return null
  const match = componentStack.match(/^\s*(?:at|in)\s+([A-Za-z0-9_$]+)/m)
  return match ? match[1] : null
}

export function buildErrorDiagnostics(
  error: Error,
  componentStack: string | null,
): ErrorDiagnostics {
  return {
    error: {
      name: error.name,
      message: error.message,
      stack: error.stack ?? null,
    },
    page: {
      url: window.location.href,
      pathname: window.location.pathname,
    },
    component: extractComponentName(componentStack),
    componentStack,
    breadcrumbs: getBreadcrumbs(),
    environment: {
      userAgent: navigator.userAgent,
      language: navigator.language,
      screenResolution: `${window.screen.width}x${window.screen.height}`,
      viewport: `${window.innerWidth}x${window.innerHeight}`,
      appVersion: APP_VERSION,
      commit: APP_COMMIT,
      timestamp: new Date().toISOString(),
    },
  }
}
