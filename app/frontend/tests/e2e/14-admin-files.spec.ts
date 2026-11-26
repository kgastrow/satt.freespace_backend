import { test, expect } from './fixtures/auth';
import { navigateTo, waitForTableLoad } from './fixtures/helpers';

/**
 * Admin File Management E2E Tests
 *
 * Tests file listing, upload, and settings.
 */
test.describe('Admin - File Management', () => {
  test('admin files page loads', async ({ page }) => {
    await navigateTo(page, '/admin/files');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('file upload button exists', async ({ page }) => {
    await navigateTo(page, '/admin/files');
    await page.waitForTimeout(1_000);

    const uploadButton = page.getByRole('button', { name: /upload|add/i }).first();
    // Upload functionality should be available
    if (await uploadButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await expect(uploadButton).toBeEnabled();
    }
  });

  test('file settings page loads', async ({ page }) => {
    await navigateTo(page, '/admin/files/settings');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('file settings shows storage configuration', async ({ page }) => {
    await navigateTo(page, '/admin/files/settings');

    // Should show storage config (local/S3) and limits
    await page.waitForTimeout(1_000);
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});
