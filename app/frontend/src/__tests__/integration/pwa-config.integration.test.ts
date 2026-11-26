/// <reference types="node" />
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync, statSync } from 'fs'
import { resolve } from 'path'

const repoRoot = resolve(__dirname, '../../..')
const viteConfig = readFileSync(resolve(repoRoot, 'vite.config.ts'), 'utf-8')
const indexHtml = readFileSync(resolve(repoRoot, 'index.html'), 'utf-8')
const pub = (p: string) => resolve(repoRoot, 'public', p)

describe('PWA manifest', () => {
  it('declares standalone display and the dark theme color', () => {
    expect(viteConfig).toMatch(/display:\s*'standalone'/)
    expect(viteConfig).toMatch(/theme_color:\s*'#0f172a'/)
  })

  it('no longer references the rocket.svg placeholder icon', () => {
    expect(viteConfig).not.toMatch(/rocket\.svg/)
  })

  it('declares 192 and 512 any-purpose PNG icons', () => {
    expect(viteConfig).toMatch(/src:\s*'\/icons\/icon-192\.png'[\s\S]*?purpose:\s*'any'/)
    expect(viteConfig).toMatch(/src:\s*'\/icons\/icon-512\.png'[\s\S]*?purpose:\s*'any'/)
  })

  it('declares 192 and 512 maskable PNG icons', () => {
    expect(viteConfig).toMatch(/src:\s*'\/icons\/icon-maskable-192\.png'[\s\S]*?purpose:\s*'maskable'/)
    expect(viteConfig).toMatch(/src:\s*'\/icons\/icon-maskable-512\.png'[\s\S]*?purpose:\s*'maskable'/)
  })

  it('declares a 180x180 apple-touch-icon entry', () => {
    expect(viteConfig).toMatch(/src:\s*'\/apple-touch-icon\.png'[\s\S]*?sizes:\s*'180x180'/)
  })
})

describe('PWA icon assets', () => {
  const iconPaths = [
    'icons/icon-192.png',
    'icons/icon-512.png',
    'icons/icon-maskable-192.png',
    'icons/icon-maskable-512.png',
    'icons/favicon-16.png',
    'icons/favicon-32.png',
    'apple-touch-icon.png',
  ]

  it.each(iconPaths)('%s exists and is a non-empty PNG', (p) => {
    const full = pub(p)
    expect(existsSync(full), `missing ${p}`).toBe(true)
    const buf = readFileSync(full)
    expect(buf.length).toBeGreaterThan(0)
    // PNG magic bytes: 89 50 4E 47 0D 0A 1A 0A
    expect(buf.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a')
    expect(statSync(full).size).toBeGreaterThan(100)
  })
})

describe('iOS / mobile install meta tags (index.html)', () => {
  it('declares theme-color matching the manifest', () => {
    expect(indexHtml).toMatch(/<meta\s+name="theme-color"\s+content="#0f172a"/)
  })

  it('opts into iOS standalone mode', () => {
    expect(indexHtml).toMatch(/<meta\s+name="apple-mobile-web-app-capable"\s+content="yes"/)
    expect(indexHtml).toMatch(/<meta\s+name="mobile-web-app-capable"\s+content="yes"/)
  })

  it('sets iOS status bar style for dark theme', () => {
    expect(indexHtml).toMatch(/apple-mobile-web-app-status-bar-style"\s+content="black-translucent"/)
  })

  it('links the apple-touch-icon', () => {
    expect(indexHtml).toMatch(/<link\s+rel="apple-touch-icon"\s+sizes="180x180"\s+href="\/apple-touch-icon\.png"/)
  })

  it('links PNG favicons for 16 and 32 sizes', () => {
    expect(indexHtml).toMatch(/href="\/icons\/favicon-16\.png"/)
    expect(indexHtml).toMatch(/href="\/icons\/favicon-32\.png"/)
  })

  it('uses viewport-fit=cover for iOS safe-area', () => {
    expect(indexHtml).toMatch(/viewport-fit=cover/)
  })

  it('declares the app title for iOS home-screen install', () => {
    expect(indexHtml).toMatch(/apple-mobile-web-app-title"\s+content="AYZER"/)
  })
})

describe('Workbox runtime caching strategies', () => {
  it('uses NetworkFirst with a short TTL for /version.json', () => {
    expect(viteConfig).toMatch(
      /urlPattern:\s*\/\\\/version\\\.json\/[\s\S]*?handler:\s*'NetworkFirst'[\s\S]*?maxAgeSeconds:\s*60/
    )
  })

  it('uses NetworkFirst for API requests', () => {
    expect(viteConfig).toMatch(
      /urlPattern:\s*\/\^https:\\\/\\\/\.\*\\\/api\\\/\/[\s\S]*?handler:\s*'NetworkFirst'/
    )
  })

  // Hashed asset filenames are immutable, so CacheFirst is correct here - a
  // revalidation round-trip could never return anything different.
  it('uses CacheFirst for static JS/CSS/fonts', () => {
    expect(viteConfig).toMatch(
      /urlPattern:\s*\/\\\.\(\?:js\|css\|woff2\?\)\$\/[\s\S]*?handler:\s*'CacheFirst'/
    )
  })

  it('uses the SPA shell as the navigation fallback and excludes /api/', () => {
    expect(viteConfig).toMatch(/navigateFallback:\s*'\/index\.html'/)
    expect(viteConfig).toMatch(/navigateFallbackDenylist:\s*\[\/\^\\\/api\\\/\/\]/)
  })

  it('keeps version.json out of the precache manifest', () => {
    expect(viteConfig).toMatch(/globIgnores:\s*\[\s*'\*\*\/version\.json'(,\s*'[^']+')*\s*\]/)
  })

  // The push handlers live in a separate file so the worker can stay on
  // workbox `generateSW`; switching to `injectManifest` to get them is a much
  // heavier change. The payload shape is a contract with web_push_provider.py.
  it('pulls the Web Push handlers into the generated worker', () => {
    expect(viteConfig).toMatch(/importScripts:\s*\['\/sw-push\.js'\]/)
    expect(existsSync(pub('sw-push.js'))).toBe(true)
  })
})

describe('PWA is dev-gated', () => {
  it('disables the service worker unless VITE_ENABLE_PWA=true', () => {
    expect(viteConfig).toMatch(/disable:\s*process\.env\.VITE_ENABLE_PWA\s*!==\s*'true'/)
  })

  // A new worker must stage the whole build and wait. Promoting it on sight
  // prunes the precache under the page that is still running the old build,
  // whose next lazy chunk then 404s.
  it('stages updates instead of promoting them on sight', () => {
    expect(viteConfig).toMatch(/registerType:\s*'prompt'/)
    expect(viteConfig).toMatch(/skipWaiting:\s*false/)
    expect(viteConfig).toMatch(/cleanupOutdatedCaches:\s*true/)
  })

  // Gated by skipWaiting above, so this only affects a first-ever visit - where
  // dropping it would mean no offline shell and no runtime cache at all.
  it('claims first-visit clients so the offline shell works immediately', () => {
    expect(viteConfig).toMatch(/clientsClaim:\s*true/)
  })
})

describe('Offline fallback page', () => {
  it('offline.html exists and is non-trivial', () => {
    const p = pub('offline.html')
    expect(existsSync(p)).toBe(true)
    expect(statSync(p).size).toBeGreaterThan(200)
  })
})

/**
 * The commit hash is the build's identity: version.json advertises it, the
 * update check compares it, and `X-App-Commit` reports it on every API call.
 * Falling back to "development" silently produces a valid artifact that no
 * client can distinguish from any other release.
 */
describe('Build identity', () => {
  it('refuses to produce a build that cannot name its commit', () => {
    expect(viteConfig).toMatch(/function assertBuildIsIdentifiable/)
    expect(viteConfig).toMatch(/throw new Error\(\s*`Refusing to build/)
  })

  it('only enforces it on a real build, so dev and tests still run', () => {
    expect(viteConfig).toMatch(/config\.command === 'build'\)\s*assertBuildIsIdentifiable\(\)/)
  })

  it('keeps an explicit escape hatch rather than inviting the check to be deleted', () => {
    expect(viteConfig).toMatch(
      /ALLOW_UNVERSIONED_BUILD = process\.env\.ALLOW_UNVERSIONED_BUILD === 'true'/
    )
  })

  it('resolves the metadata once, so version.json and the bundle agree', () => {
    // Three `define` entries plus version.json read this. Un-memoised, each
    // call took a fresh timestamp and the two disagreed.
    expect(viteConfig).toMatch(/if \(!buildMetadata\) \{/)
  })
})
