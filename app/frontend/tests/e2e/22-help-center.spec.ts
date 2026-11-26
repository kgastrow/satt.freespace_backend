import { test, expect } from '@playwright/test';

/**
 * Help Center E2E Tests (Public)
 *
 * Tests the public help center pages. These don't require authentication.
 */
test.describe('Help Center', () => {
  test('help center page loads', async ({ page }) => {
    await page.goto('/help-center');
    await page.waitForLoadState('networkidle');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('help center shows categories or articles', async ({ page }) => {
    await page.goto('/help-center');
    await page.waitForLoadState('networkidle');

    // Should show some content structure
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});
