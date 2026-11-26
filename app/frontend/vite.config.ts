import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'
import { compression } from 'vite-plugin-compression2'
import path from 'path'
import fs from 'fs'
import { execSync } from 'child_process'

// The commit hash IS the build's identity: it is what version.json advertises,
// what the update check compares, and what `X-App-Commit` reports on every API
// call. A build that cannot name its own commit is untraceable in production.
const UNVERSIONED_COMMIT = 'development'

// Escape hatch for a deliberate build from a source tree with no git history
// (a tarball, a vendored copy). Nothing routine should need it.
const ALLOW_UNVERSIONED_BUILD = process.env.ALLOW_UNVERSIONED_BUILD === 'true'

/** Whatever git said when it refused, so the failure can quote it. */
let gitCommitError: string | null = null

function getGitCommitHash(): string {
  try {
    // stderr is captured rather than inherited: it is reported deliberately
    // below instead of scrolling past in the middle of the build log.
    return execSync('git rev-parse HEAD', {
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim()
  } catch (error) {
    const stderr = (error as { stderr?: Buffer | string }).stderr
    gitCommitError = String(stderr ?? (error as Error).message).trim()
    return UNVERSIONED_COMMIT
  }
}

// Resolved once. Three `define` entries and version.json all read this, and
// before it was memoised each call re-ran git AND took a fresh timestamp - so
// the bundle's VITE_BUILD_TIME and version.json's build_time disagreed.
let buildMetadata: {
  VITE_BUILD_VERSION: string
  VITE_BUILD_COMMIT: string
  VITE_BUILD_TIME: string
} | null = null

function getBuildMetadata() {
  if (!buildMetadata) {
    buildMetadata = {
      VITE_BUILD_VERSION: process.env.npm_package_version || '0.0.0',
      VITE_BUILD_COMMIT: getGitCommitHash(),
      VITE_BUILD_TIME: new Date().toISOString(),
    }
  }
  return buildMetadata
}

/**
 * Refuse to produce a production bundle that cannot identify itself.
 *
 * Falling back to 'development' silently means the build succeeds, the artifact
 * is valid, and version.json ships `commit_hash: "development"`. Every client
 * then reports the same commit forever, so the version check can never see a
 * difference and nothing downstream can tell two releases apart. Failing the
 * build is recoverable in a minute; shipping an unidentifiable one is not
 * noticed for weeks.
 */
function assertBuildIsIdentifiable() {
  if (getBuildMetadata().VITE_BUILD_COMMIT !== UNVERSIONED_COMMIT) return

  const detail = gitCommitError ? `\n\ngit said:\n  ${gitCommitError}` : ''

  if (ALLOW_UNVERSIONED_BUILD) {
    console.warn(
      `\n[build] WARNING: no git commit - this build reports "${UNVERSIONED_COMMIT}".` +
        `\n[build] Update detection and per-build API attribution will not work.` +
        `\n[build] Continuing because ALLOW_UNVERSIONED_BUILD=true.${detail}\n`
    )
    return
  }

  throw new Error(
    `Refusing to build: \`git rev-parse HEAD\` failed, so this bundle cannot ` +
      `identify which commit it came from.${detail}\n\n` +
      `Usual causes, in order of likelihood:\n` +
      `  1. The repo is owned by a different user than the one building.\n` +
      `     Fix: git config --global --add safe.directory ${path.resolve(__dirname, '../..')}\n` +
      `  2. This source tree has no .git (copied by rsync/scp/tarball rather than cloned).\n` +
      `  3. git is not installed on this machine.\n\n` +
      `If you genuinely need an unidentifiable build, set ALLOW_UNVERSIONED_BUILD=true.\n`
  )
}

// Read port from .ports.env if it exists
function getServerConfig(): { port: number; strictPort: boolean } {
  const portsEnvPath = path.resolve(__dirname, '../../.ports.env')
  if (fs.existsSync(portsEnvPath)) {
    const content = fs.readFileSync(portsEnvPath, 'utf-8')
    const match = content.match(/^FRONTEND_PORT=(\d+)/m)
    if (match) {
      // Use strict port when explicitly configured
      return { port: parseInt(match[1], 10), strictPort: true }
    }
  }
  // Default: allow port incrementing
  return { port: 5173, strictPort: false }
}

// Generate version.json file with build metadata
function generateVersionJson(outputDir: string) {
  const metadata = getBuildMetadata()
  const versionJson = JSON.stringify(
    {
      version: metadata.VITE_BUILD_VERSION,
      commit_hash: metadata.VITE_BUILD_COMMIT,
      build_time: metadata.VITE_BUILD_TIME,
    },
    null,
    2
  )
  fs.writeFileSync(path.resolve(outputDir, 'version.json'), versionJson)
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      disable: process.env.VITE_ENABLE_PWA !== 'true',
      registerType: 'prompt',
      manifest: {
        name: process.env.VITE_PWA_APP_NAME || 'FREESPACE',
        short_name: process.env.VITE_PWA_APP_NAME || 'FREESPACE',
        description: 'Multi-tenant application',
        display: 'standalone',
        background_color: '#ffffff',
        theme_color: '#0f172a',
        icons: [
          {
            src: '/icons/icon-192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'any',
          },
          {
            src: '/icons/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any',
          },
          {
            src: '/icons/icon-maskable-192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'maskable',
          },
          {
            src: '/icons/icon-maskable-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
          {
            src: '/apple-touch-icon.png',
            sizes: '180x180',
            type: 'image/png',
            purpose: 'any',
          },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        // Precaching the version file would defeat the version check.
        globIgnores: ['**/version.json'],
        // Pull the Web Push `push` / `notificationclick` handlers into the
        // generated worker. `importScripts` keeps us on `generateSW` (precache +
        // runtime caching) rather than switching to the heavier `injectManifest`.
        importScripts: ['/sw-push.js'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
        navigateFallbackAllowlist: [/^\/(?!api\/)/],
        // The new worker precaches the whole build, then parks in `waiting`
        // until the user asks for it (src/lib/swUpdate.ts). `skipWaiting: true`
        // promoted it the moment it was detected, which pruned the precache out
        // from under the still-open page - its next lazy chunk then missed the
        // cache, hit the network, and got a real 404 from the `/assets/` rule.
        skipWaiting: false,
        // Independent of the above, and still wanted: it only matters when a
        // worker activates, which is now gated. Without it a first-ever visitor
        // is never controlled, so there is no offline shell and no runtime cache
        // ever populates.
        clientsClaim: true,
        cleanupOutdatedCaches: true,
        runtimeCaching: [
          {
            urlPattern: /\/version\.json/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'version-check',
              expiration: { maxEntries: 1, maxAgeSeconds: 60 },
            },
          },
          {
            urlPattern: /^https:\/\/.*\/api\//,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: { maxEntries: 50, maxAgeSeconds: 300 },
            },
          },
          {
            // Hashed JS/CSS/font filenames are immutable — CacheFirst avoids
            // the useless background revalidation that StaleWhileRevalidate does.
            urlPattern: /\.(?:js|css|woff2?)$/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'static-cache',
              expiration: { maxEntries: 100, maxAgeSeconds: 60 * 60 * 24 * 30 },
            },
          },
        ],
      },
    }),
    {
      name: 'generate-version-json',
      configResolved(config) {
        // Only a real build is held to this. `vite dev` and the test runner
        // legitimately have no commit to report and must keep working.
        if (config.command === 'build') assertBuildIsIdentifiable()
        // Generate version.json in public/ for dev server
        generateVersionJson(path.resolve(__dirname, 'public'))
      },
      writeBundle() {
        // Generate version.json in dist/ during production build
        generateVersionJson(path.resolve(__dirname, 'dist'))
      },
    },
    // Gzip compression for production builds
    compression({
      algorithms: ['gzip'],
      exclude: [/\.(br)$/, /\.(gz)$/],
      threshold: 1024, // Only compress files > 1KB
    }),
    // Brotli compression for modern browsers
    compression({
      algorithms: ['brotliCompress'],
      exclude: [/\.(br)$/, /\.(gz)$/],
      threshold: 1024,
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    ...getServerConfig(),
    proxy: {
      '/api': {
        target: `http://localhost:${process.env.BACKEND_PORT || '8000'}`,
        changeOrigin: true,
      },
    },
  },
  define: {
    'import.meta.env.VITE_BUILD_VERSION': JSON.stringify(getBuildMetadata().VITE_BUILD_VERSION),
    'import.meta.env.VITE_BUILD_COMMIT': JSON.stringify(getBuildMetadata().VITE_BUILD_COMMIT),
    'import.meta.env.VITE_BUILD_TIME': JSON.stringify(getBuildMetadata().VITE_BUILD_TIME),
  },
  build: {
    rollupOptions: {
      output: {
        // Manual chunk splitting for better caching
        manualChunks: {
          // Core React runtime
          'react-vendor': ['react', 'react-dom'],
          // Routing
          'router': ['react-router-dom'],
          // State management
          'redux': ['@reduxjs/toolkit', 'react-redux'],
          // UI components library (Radix)
          'ui-vendor': [
            '@radix-ui/react-dialog',
            '@radix-ui/react-dropdown-menu',
            '@radix-ui/react-popover',
            '@radix-ui/react-select',
            '@radix-ui/react-tabs',
            '@radix-ui/react-tooltip',
            '@radix-ui/react-accordion',
            '@radix-ui/react-avatar',
            '@radix-ui/react-checkbox',
            '@radix-ui/react-label',
            '@radix-ui/react-switch',
          ],
          // Form handling
          'forms': ['react-hook-form', '@hookform/resolvers', 'zod'],
          // i18n
          'i18n': ['i18next', 'react-i18next', 'i18next-browser-languagedetector'],
          // Date utilities
          'date': ['date-fns'],
          // Icons
          'icons': ['lucide-react'],
        },
      },
    },
    // Generate source maps for debugging (optional, disable in production if needed)
    sourcemap: false,
    // Increase chunk size warning limit (since we're splitting deliberately)
    chunkSizeWarningLimit: 600,
  },
})
