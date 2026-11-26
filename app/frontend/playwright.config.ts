import { defineConfig, devices } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

/**
 * E2E Test Configuration
 *
 * Automatically starts backend, ARQ worker, and frontend dev servers.
 * Auth setup seeds a smoke test user via the backend seed script.
 *
 * Port allocation uses ADW_CODEBASE_INDEX to avoid conflicts when multiple
 * codebases run e2e tests simultaneously. Default (index 0) uses ports
 * 8100 (backend) and 5174 (frontend). Each codebase index offsets by 10.
 *
 * Servers use reuseExistingServer: true so both VS Code's Playwright
 * extension and CLI runs can share the same server instances. If no
 * server is running, Playwright starts one automatically.
 *
 * Environment variables:
 *   E2E_BACKEND_PORT  - Override backend port (default: derived from index)
 *   E2E_FRONTEND_PORT - Override frontend port (default: derived from index)
 *   ADW_CODEBASE_INDEX - Codebase slot for port partitioning (default: 0)
 *   E2E_ADW_ID        - ADW identifier for org slug (default: e2e-playwright)
 *   E2E_BASE_URL      - Override frontend base URL entirely
 *
 * Run: npx playwright test
 * Debug: npx playwright test --debug
 * UI: npx playwright test --ui
 */

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const backendDir = path.resolve(__dirname, '../backend');
const authDir = path.resolve(__dirname, 'tests/e2e/.auth');
const authStateFile = (browser: string) => path.resolve(authDir, `storage-state-${browser}.json`);

// E2E org slug must match the seed script output (smoke-test-{ADW_ID})
const E2E_ADW_ID = process.env.E2E_ADW_ID || 'e2e-playwright';
const E2E_ORG_SLUG = `smoke-test-${E2E_ADW_ID}`;

// Resource allocation: derive from ADW_CODEBASE_INDEX to avoid conflicts
// across simultaneous test runs on different codebases.
//
// Ports: backend 8100, frontend 5174. Each codebase index offsets by 10.
// Redis: each codebase's e2e gets its own Redis DB to avoid cache and
// pub/sub collisions across simultaneous test runs.
//   DBs 0-1:   main app (cache=0, ARQ=1)
//   DBs 2-14:  ADW worktrees
//   DB 15+:    e2e tests (one DB per codebase index: 15, 16, 17, ...)
// Cache and ARQ share a single DB — key patterns (arq:*, jwt:*, user:*, ws:*)
// don't overlap, same approach as ADW worktrees.
// setup-system-deps.sh sets databases=165, supporting up to 150 e2e DBs.
const CODEBASE_INDEX = parseInt(process.env.ADW_CODEBASE_INDEX || '0', 10);
const PORT_OFFSET = CODEBASE_INDEX * 10;
const E2E_BACKEND_PORT = parseInt(process.env.E2E_BACKEND_PORT || String(8100 + PORT_OFFSET), 10);
const E2E_FRONTEND_PORT = parseInt(process.env.E2E_FRONTEND_PORT || String(5174 + PORT_OFFSET), 10);
const E2E_REDIS_DB = 15 + CODEBASE_INDEX;
const E2E_REDIS_URL = process.env.REDIS_URL || `redis://localhost:6379/${E2E_REDIS_DB}`;

// Expose backend port to test process so apiCall() and auth fixtures use the right URL.
// This must be set before tests import helpers.ts which reads E2E_API_URL at module load.
process.env.E2E_API_URL = process.env.E2E_API_URL || `http://localhost:${E2E_BACKEND_PORT}`;

// Redis FLUSHDB is done in global-setup.ts (runs every time, regardless of
// whether invoked from VS Code or CLI). No config-level cleanup needed.

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // Serial execution — tests share seeded state
  reporter: [
    ['html', { open: 'never' }],
    ['list'],
  ],
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: process.env.E2E_BASE_URL || `http://localhost:${E2E_FRONTEND_PORT}`,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  projects: [
    // --- Per-browser setup projects ---
    // Each browser needs its own login + storageState because cookie/storage
    // formats are browser-specific. The seed (DB + token generation) only runs
    // once; the browser login runs per engine.
    {
      name: 'setup-chromium',
      testMatch: /global-setup\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'setup-firefox',
      testMatch: /global-setup\.ts/,
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'setup-webkit',
      testMatch: /global-setup\.ts/,
      use: { ...devices['Desktop Safari'] },
    },

    // --- Chromium ---
    {
      name: 'chromium-auth',
      testMatch: /01-auth-login\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['setup-chromium'],
    },
    {
      name: 'chromium-public',
      testMatch: /0[34]-auth-.*\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['setup-chromium'],
    },
    {
      name: 'chromium',
      testIgnore: /(01-auth-login|0[34]-auth-.*)\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        storageState: authStateFile('chromium'),
      },
      dependencies: ['setup-chromium'],
    },
    // --- Firefox ---
    {
      name: 'firefox-auth',
      testMatch: /01-auth-login\.spec\.ts/,
      use: { ...devices['Desktop Firefox'] },
      dependencies: ['setup-firefox'],
    },
    {
      name: 'firefox-public',
      testMatch: /0[34]-auth-.*\.spec\.ts/,
      use: { ...devices['Desktop Firefox'] },
      dependencies: ['setup-firefox'],
    },
    {
      name: 'firefox',
      testIgnore: /(01-auth-login|0[34]-auth-.*)\.spec\.ts/,
      use: {
        ...devices['Desktop Firefox'],
        storageState: authStateFile('firefox'),
      },
      dependencies: ['setup-firefox'],
    },
    // --- WebKit (Safari) ---
    {
      name: 'webkit-auth',
      testMatch: /01-auth-login\.spec\.ts/,
      use: { ...devices['Desktop Safari'] },
      dependencies: ['setup-webkit'],
    },
    {
      name: 'webkit-public',
      testMatch: /0[34]-auth-.*\.spec\.ts/,
      use: { ...devices['Desktop Safari'] },
      dependencies: ['setup-webkit'],
    },
    {
      name: 'webkit',
      testIgnore: /(01-auth-login|0[34]-auth-.*)\.spec\.ts/,
      use: {
        ...devices['Desktop Safari'],
        storageState: authStateFile('webkit'),
      },
      dependencies: ['setup-webkit'],
    },
  ],

  /* Start backend, ARQ worker, and frontend dev servers.
   * reuseExistingServer: true allows VS Code and CLI to share servers.
   * gracefulShutdown ensures clean teardown.
   * All backend processes share the same isolated Redis DB. */
  webServer: [
    {
      command: `cd ${backendDir} && .venv/bin/uvicorn main:app --host 0.0.0.0 --port ${E2E_BACKEND_PORT}`,
      port: E2E_BACKEND_PORT,
      reuseExistingServer: true,
      timeout: 30_000,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 5_000 },
      stdout: 'pipe',
      stderr: 'pipe',
      env: {
        ...process.env,
        REDIS_URL: E2E_REDIS_URL,
        ARQ_REDIS_URL: E2E_REDIS_URL,
        CORS_ALLOWED_ORIGINS: `http://localhost:${E2E_FRONTEND_PORT},http://localhost:5173`,
        RATE_LIMIT_ENABLED: 'false',
        COOKIE_SECURE: 'false',
      },
    },
    {
      // ARQ background worker for async jobs. Has no port — Playwright starts
      // it and considers it immediately ready. With reuseExistingServer: true
      // and no port, Playwright will always start a new one. Duplicate workers
      // on the same Redis queue are harmless (ARQ uses distributed locking).
      command: `cd ${backendDir} && .venv/bin/arq src.workers.worker.WorkerSettings`,
      reuseExistingServer: true,
      timeout: 10_000,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 3_000 },
      stdout: 'pipe',
      stderr: 'pipe',
      env: {
        ...process.env,
        REDIS_URL: E2E_REDIS_URL,
        ARQ_REDIS_URL: E2E_REDIS_URL,
      },
    },
    {
      command: `npx vite --port ${E2E_FRONTEND_PORT} --mode e2e`,
      port: E2E_FRONTEND_PORT,
      reuseExistingServer: true,
      timeout: 15_000,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 3_000 },
      stdout: 'pipe',
      stderr: 'pipe',
      env: {
        ...process.env,
        VITE_ORG_SLUG: E2E_ORG_SLUG,
        VITE_API_URL: `http://localhost:${E2E_BACKEND_PORT}/api/v1`,
        VITE_WS_URL: `ws://localhost:${E2E_BACKEND_PORT}`,
      },
    },
  ],
});
