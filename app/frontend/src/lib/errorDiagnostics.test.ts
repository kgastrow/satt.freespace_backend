import { beforeEach, describe, expect, it, vi } from 'vitest'

let diag: typeof import('./errorDiagnostics')
let breadcrumbs: typeof import('./errorBreadcrumbs')

beforeEach(async () => {
  vi.resetModules()
  breadcrumbs = await import('./errorBreadcrumbs')
  diag = await import('./errorDiagnostics')
})

describe('extractComponentName', () => {
  it('returns null for null or empty input', () => {
    expect(diag.extractComponentName(null)).toBeNull()
    expect(diag.extractComponentName('')).toBeNull()
  })

  it('extracts the component from a React 19 "at" frame', () => {
    const stack = '\n    at Boom (http://localhost/src/pages/dev/CrashTestPage.tsx:6:9)'
    expect(diag.extractComponentName(stack)).toBe('Boom')
  })

  it('extracts the component from a legacy "in" frame', () => {
    const stack = '\n    in Boom (at CrashTestPage.tsx:6)\n    in CardContent'
    expect(diag.extractComponentName(stack)).toBe('Boom')
  })

  it('returns the first (closest) frame when several are present', () => {
    const stack = '\n    at Inner\n    at Outer\n    at App'
    expect(diag.extractComponentName(stack)).toBe('Inner')
  })

  it('handles component names with digits and $', () => {
    const stack = '\n    at Form2$Inner (file.tsx:1:1)'
    expect(diag.extractComponentName(stack)).toBe('Form2$Inner')
  })
})

describe('buildErrorDiagnostics', () => {
  const componentStack = '\n    at Boom (http://localhost/src/pages/dev/CrashTestPage.tsx:6:9)'

  it('captures error name, message, and stack', () => {
    const error = new Error('boom')
    const result = diag.buildErrorDiagnostics(error, componentStack)
    expect(result.error.name).toBe('Error')
    expect(result.error.message).toBe('boom')
    expect(result.error.stack).toBe(error.stack)
  })

  it('uses null when the error has no stack', () => {
    const error = new Error('boom')
    error.stack = undefined
    expect(diag.buildErrorDiagnostics(error, componentStack).error.stack).toBeNull()
  })

  it('captures the current page from window.location', () => {
    const result = diag.buildErrorDiagnostics(new Error('x'), componentStack)
    expect(result.page.url).toBe(window.location.href)
    expect(result.page.pathname).toBe(window.location.pathname)
  })

  it('derives the component name and passes the raw stack through', () => {
    const result = diag.buildErrorDiagnostics(new Error('x'), componentStack)
    expect(result.component).toBe('Boom')
    expect(result.componentStack).toBe(componentStack)
  })

  it('includes the current breadcrumb trail', () => {
    breadcrumbs.recordBreadcrumb('navigation', 'Navigated to /dev/crash')
    breadcrumbs.recordBreadcrumb('click', 'Clicked "Trigger render error"')

    const result = diag.buildErrorDiagnostics(new Error('x'), componentStack)
    expect(result.breadcrumbs.map((c) => c.label)).toEqual([
      'Navigated to /dev/crash',
      'Clicked "Trigger render error"',
    ])
  })

  it('captures environment metadata', () => {
    const { environment } = diag.buildErrorDiagnostics(new Error('x'), componentStack)
    expect(environment.userAgent).toBe(navigator.userAgent)
    expect(environment.language).toBe(navigator.language)
    expect(environment.screenResolution).toBe(`${window.screen.width}x${window.screen.height}`)
    expect(environment.viewport).toBe(`${window.innerWidth}x${window.innerHeight}`)
    expect(environment.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T/)
    // Build vars are unset under test → documented fallbacks
    expect(environment.appVersion).toBe('0.0.0')
    expect(environment.commit).toBe('development')
  })
})
