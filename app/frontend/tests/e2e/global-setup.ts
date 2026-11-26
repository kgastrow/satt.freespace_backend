import { test as setup, expect } from '@playwright/test';
import { execSync } from 'child_process';
import { seedAuthTokens } from './fixtures/auth';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const AUTH_DIR = path.resolve(__dirname, '.auth');
const AUTH_TOKENS_FILE = path.resolve(AUTH_DIR, 'auth-tokens.json');

/**
 * Global setup: seeds the smoke test user, performs a real browser login,
 * and saves the full browser state (cookies including httpOnly + localStorage).
 *
 * Runs once per browser engine (setup-chromium, setup-firefox, etc.).
 * The DB seed only writes if the user doesn't exist yet, so running
 * multiple times is safe.
 */
setup('seed auth and store state', async ({ page, context }, testInfo) => {
  // Derive browser label from project name (e.g., "setup-firefox" → "firefox")
  const projectName = testInfo.project.name || '';
  const browser = projectName.replace('setup-', '') || 'chromium';

  // Step 0: Flush e2e Redis DB once (first setup only) to clear stale
  // rate-limit counters and cached state. Subsequent browser setups skip
  // this to avoid clearing state that earlier setups depend on.
  if (!process.env._E2E_REDIS_FLUSHED) {
    process.env._E2E_REDIS_FLUSHED = '1';
    const codebaseIndex = parseInt(process.env.ADW_CODEBASE_INDEX || '0', 10);
    const redisDb = 15 + codebaseIndex;
    try {
      execSync(`redis-cli -n ${redisDb} FLUSHDB 2>/dev/null`, {
        stdio: 'ignore', timeout: 3_000,
      });
    } catch { /* Redis not available */ }
  }

  // Step 1: Seed the user in the database
  const auth = await seedAuthTokens();
  fs.mkdirSync(AUTH_DIR, { recursive: true });
  fs.writeFileSync(AUTH_TOKENS_FILE, JSON.stringify(auth, null, 2));

  // Step 2: Perform a real browser login to get proper cookies
  await page.goto('/login');

  // Email step
  await page.fill('input#email', auth.email);
  await page.getByRole('button', { name: /continue/i }).click();

  // Password step
  await page.locator('input#password').waitFor({ state: 'visible', timeout: 10_000 });
  await page.fill('input#password', 'SmokeTest@123');
  await page.getByRole('button', { name: /login|sign in/i }).click();

  // Wait for login to complete — app should load the dashboard
  await page.waitForURL('**/dashboard**', { timeout: 15_000 }).catch(() => {
    // Some setups redirect elsewhere
  });
  // Ensure we're past the login page
  await expect(page.locator('input#email')).not.toBeVisible({ timeout: 15_000 });

  // Step 3: Verify cookies are set (the login endpoint sets httpOnly refresh_token)
  const cookies = await context.cookies();
  const refreshCookie = cookies.find((c) => c.name === 'refresh_token');
  if (!refreshCookie) {
    console.warn('WARNING: No refresh_token cookie found after login. Cookies:', cookies.map(c => c.name));
  }

  // Step 4: Save per-browser storage state (uses project name, not engine name,
  // because Edge and Chrome both report browserName="chromium")
  const stateFile = path.resolve(AUTH_DIR, `storage-state-${browser}.json`);
  await context.storageState({ path: stateFile });

  const saved = JSON.parse(fs.readFileSync(stateFile, 'utf-8'));
  console.log(`[${browser}] Saved ${saved.cookies?.length || 0} cookies, ${saved.origins?.length || 0} origins`);
});
