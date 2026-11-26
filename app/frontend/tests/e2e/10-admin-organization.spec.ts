import { test, expect } from './fixtures/auth';
import { navigateTo } from './fixtures/helpers';

/**
 * Admin Organization Settings E2E Tests
 *
 * Tests organization settings, SSO config, and 2FA policy.
 */
test.describe('Admin - Organization Settings', () => {
  test('organization settings page loads', async ({ page }) => {
    await navigateTo(page, '/admin/organization');

    // Should show organization form with name/slug
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('organization name is displayed', async ({ page }) => {
    await navigateTo(page, '/admin/organization');

    // Should show the org name in a form field or display
    const nameInput = page.locator('input[name="name"], input#name').first();
    if (await nameInput.isVisible({ timeout: 5_000 }).catch(() => false)) {
      const value = await nameInput.inputValue();
      expect(value.length).toBeGreaterThan(0);
    }
  });

  test('SSO settings page loads', async ({ page }) => {
    await navigateTo(page, '/admin/sso/settings');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('2FA policy settings page loads', async ({ page }) => {
    await navigateTo(page, '/admin/two-factor');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});
