import { test, expect } from './fixtures/auth';
import { navigateTo, waitForTableLoad } from './fixtures/helpers';

/**
 * Admin Notifications E2E Tests
 *
 * Tests notification management: sending, templates, categories, and settings.
 */
test.describe('Admin - Notifications', () => {
  test('notifications list page loads', async ({ page }) => {
    await navigateTo(page, '/admin/notifications');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('send notification page loads with form', async ({ page }) => {
    await navigateTo(page, '/admin/notifications/send');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('bulk notifications page loads', async ({ page }) => {
    await navigateTo(page, '/admin/notifications/bulk');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('notification templates page loads', async ({ page }) => {
    await navigateTo(page, '/admin/notifications/templates');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('notification categories page loads', async ({ page }) => {
    await navigateTo(page, '/admin/notifications/categories');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('notification settings page loads', async ({ page }) => {
    await navigateTo(page, '/admin/notifications/settings');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});
