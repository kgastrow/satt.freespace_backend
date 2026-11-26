import { test, expect } from './fixtures/auth';
import { navigateTo, waitForTableLoad } from './fixtures/helpers';

/**
 * Platform Admin - Monitoring E2E Tests
 *
 * Tests metrics dashboard, background jobs, cron jobs, and request logs.
 */
test.describe('Platform Admin - Monitoring', () => {
  test('metrics page loads', async ({ page }) => {
    await navigateTo(page, '/platform-admin/metrics');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('background jobs page loads', async ({ page }) => {
    await navigateTo(page, '/platform-admin/background-jobs');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('cron jobs page loads', async ({ page }) => {
    await navigateTo(page, '/platform-admin/cron-jobs');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('request logs page loads', async ({ page }) => {
    await navigateTo(page, '/platform-admin/request-logs');
    await waitForTableLoad(page);

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});
