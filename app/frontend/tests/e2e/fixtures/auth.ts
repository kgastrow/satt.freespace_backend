import { execSync } from 'child_process';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import { test as base, type Page } from '@playwright/test';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const BACKEND_DIR = path.resolve(__dirname, '../../../../backend');
const ADW_ID = process.env.E2E_ADW_ID || 'e2e-playwright';
const AUTH_FILE = path.resolve(__dirname, '../.auth/auth-tokens.json');

export interface AuthFixture {
  accessToken: string;
  orgSlug: string;
  organizationId: string;
  userId: string;
  email: string;
}

/**
 * Seeds the smoke test user via the backend script and returns tokens.
 * The backend database must be accessible (Docker postgres + redis running).
 */
export async function seedAuthTokens(): Promise<AuthFixture> {
  try {
    const output = execSync(
      `cd ${BACKEND_DIR} && .venv/bin/python scripts/seed_smoke_test.py --adw-id ${ADW_ID}`,
      {
        encoding: 'utf-8',
        timeout: 30_000,
        env: { ...process.env, PYTHONPATH: BACKEND_DIR },
      },
    );

    // The seed script outputs pretty-printed JSON (possibly preceded by log lines).
    // Extract the JSON object from stdout.
    const jsonStart = output.indexOf('{');
    const jsonEnd = output.lastIndexOf('}');
    const result = JSON.parse(output.slice(jsonStart, jsonEnd + 1));

    return {
      accessToken: result.access_token,
      orgSlug: result.org_slug,
      organizationId: result.organization_id,
      userId: result.user_id,
      email: result.email,
    };
  } catch (error) {
    console.error('Failed to seed auth tokens. Is the database running?');
    console.error(error);
    throw error;
  }
}

/**
 * Load auth tokens from the file written by global-setup.
 * Falls back to re-seeding if the file doesn't exist.
 */
export function loadAuthTokens(): AuthFixture {
  if (fs.existsSync(AUTH_FILE)) {
    return JSON.parse(fs.readFileSync(AUTH_FILE, 'utf-8'));
  }
  throw new Error(
    `Auth tokens file not found at ${AUTH_FILE}. Run the "setup" project first.`,
  );
}

/**
 * Injects authentication into a Playwright page via addInitScript.
 * Must be called before any navigation — it runs on every page load.
 */
export async function authenticatePage(
  page: Page,
  auth: AuthFixture,
): Promise<void> {
  await page.addInitScript(
    ({ token, slug }) => {
      localStorage.setItem('access_token', token);
      localStorage.setItem('org_slug', slug);
    },
    { token: auth.accessToken, slug: auth.orgSlug },
  );
}

/**
 * Extended test fixture that provides authenticated pages.
 */
export const test = base.extend<{ auth: AuthFixture }>({
  auth: async ({}, use) => {
    const auth = loadAuthTokens();
    await use(auth);
  },
});

export { expect } from '@playwright/test';
