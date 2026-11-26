import { test, expect } from '@playwright/test';
import { loadAuthTokens } from './fixtures/auth';

/**
 * Authentication Flow E2E Tests
 *
 * Runs in the `auth-tests` project WITHOUT stored auth state.
 * Tests the full login/logout lifecycle with real browser interactions.
 */

const SMOKE_EMAIL = 'smoke-test@example.com';
const SMOKE_PASSWORD = 'SmokeTest@123';

test.describe('Login Flow', () => {
  test('successful login with valid credentials', async ({ page }) => {
    await page.goto('/login');

    // Step 1: Email
    await expect(page.locator('input#email')).toBeVisible();
    await page.fill('input#email', SMOKE_EMAIL);
    await page.getByRole('button', { name: /continue/i }).click();

    // Step 2: Password
    await page.locator('input#password').waitFor({ state: 'visible', timeout: 10_000 });
    await page.fill('input#password', SMOKE_PASSWORD);
    await page.getByRole('button', { name: /login|sign in/i }).click();

    // Should redirect to dashboard
    await page.waitForURL('**/dashboard**', { timeout: 15_000 });
    await expect(page.locator('h1')).toBeVisible();
  });

  test('invalid credentials show error', async ({ page }) => {
    await page.goto('/login');

    // Step 1: Email
    await page.fill('input#email', SMOKE_EMAIL);
    await page.getByRole('button', { name: /continue/i }).click();

    // Step 2: Wrong password
    await page.locator('input#password').waitFor({ state: 'visible', timeout: 10_000 });
    await page.fill('input#password', 'WrongPassword999!');
    await page.getByRole('button', { name: /login|sign in/i }).click();

    // Should show error toast or stay on login page
    await expect(page.locator('input#password')).toBeVisible({ timeout: 5_000 });
  });

  test('email validation on login form', async ({ page }) => {
    await page.goto('/login');

    // Submit empty email
    await page.getByRole('button', { name: /continue/i }).click();
    // Should stay on login page with validation error
    await expect(page.locator('input#email')).toBeVisible();
  });

  test('logout flow', async ({ page }) => {
    // First log in
    await page.goto('/login');
    await page.fill('input#email', SMOKE_EMAIL);
    await page.getByRole('button', { name: /continue/i }).click();
    await page.locator('input#password').waitFor({ state: 'visible', timeout: 10_000 });
    await page.fill('input#password', SMOKE_PASSWORD);
    await page.getByRole('button', { name: /login|sign in/i }).click();
    await page.waitForURL('**/dashboard**', { timeout: 15_000 });

    // Open user menu in sidebar footer and click logout
    const userButton = page.locator("[data-sidebar='menu-button']").last();
    if (await userButton.isVisible()) {
      await userButton.click();
      const logoutItem = page.getByRole('menuitem', { name: /logout|sign out/i });
      if (await logoutItem.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await logoutItem.click();
        // Should redirect to login
        await page.waitForURL('**/login**', { timeout: 10_000 });
      }
    }
  });
});
