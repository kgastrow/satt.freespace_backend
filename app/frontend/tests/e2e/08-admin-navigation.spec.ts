import { test, expect } from './fixtures/auth';
import { navigateTo } from './fixtures/helpers';

/**
 * Admin Hub Navigation E2E Tests
 *
 * Tests admin hub loads and sidebar navigation works across all admin sections.
 */
test.describe('Admin Hub Navigation', () => {
  test('admin hub loads', async ({ page }) => {
    await navigateTo(page, '/admin');

    // Should redirect to /admin/organization or show admin hub
    await page.waitForURL('**/admin/**');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('admin sidebar renders with sections', async ({ page }) => {
    await navigateTo(page, '/admin/organization');

    // Admin layout should have a sidebar with navigation links
    const sidebar = page.locator("[data-sidebar='sidebar']").first();
    await expect(sidebar).toBeVisible();
  });

  test('navigate to users page', async ({ page }) => {
    await navigateTo(page, '/admin/users');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('navigate to notifications page', async ({ page }) => {
    await navigateTo(page, '/admin/notifications');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('navigate to announcements page', async ({ page }) => {
    await navigateTo(page, '/admin/announcements');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('navigate to audit logs page', async ({ page }) => {
    await navigateTo(page, '/admin/audit-logs');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('navigate to files page', async ({ page }) => {
    await navigateTo(page, '/admin/files');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('navigate to API keys page', async ({ page }) => {
    await navigateTo(page, '/admin/api-keys');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});
