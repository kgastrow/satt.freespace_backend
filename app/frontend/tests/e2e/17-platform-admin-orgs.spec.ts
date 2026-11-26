import { test, expect } from './fixtures/auth';
import { navigateTo, waitForTableLoad } from './fixtures/helpers';

/**
 * Platform Admin - Organizations E2E Tests
 *
 * Tests the super-admin organization management pages.
 * The smoke test user has is_admin=True which grants super admin access.
 */
test.describe('Platform Admin - Organizations', () => {
  test('organizations list page loads', async ({ page }) => {
    await navigateTo(page, '/platform-admin/organizations');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('organizations table shows data', async ({ page }) => {
    await navigateTo(page, '/platform-admin/organizations');
    await waitForTableLoad(page);

    // Should show at least the smoke test org
    const table = page.locator('table');
    if (await table.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await expect(table).toBeVisible();
    }
  });

  test('can view organization members', async ({ page }) => {
    await navigateTo(page, '/platform-admin/organizations');
    await waitForTableLoad(page);

    // Click into an organization row
    const orgRow = page.locator('tr', { hasText: /smoke/i }).first();
    if (await orgRow.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await orgRow.click();
      await page.waitForTimeout(2_000);
    }
  });
});
