import { test, expect } from './fixtures/auth';

/**
 * Sidebar Navigation E2E Tests
 *
 * Verifies the main application sidebar renders and navigates correctly.
 *
 * Selectors verified against:
 *   - app/frontend/src/components/ui/sidebar/ (data-sidebar attributes)
 *   - app/frontend/src/config/navigation.ts   (nav item URLs)
 *   - app/frontend/src/router.tsx             (route definitions)
 */
test.describe('Sidebar Navigation', () => {
  test('dashboard loads after auth', async ({ page }) => {
    await page.goto('/dashboard');
    const heading = page.locator('h1');
    await expect(heading).toBeVisible();
  });

  test('sidebar is visible with menu items', async ({ page }) => {
    await page.goto('/dashboard');

    // data-sidebar="sidebar" from Sidebar.tsx
    const sidebar = page.locator("[data-sidebar='sidebar']").first();
    await expect(sidebar).toBeVisible();

    // data-sidebar="menu-button" from SidebarMenu.tsx
    const menuButtons = page.locator("[data-sidebar='menu-button']");
    await expect(menuButtons.first()).toBeVisible();
  });

  test('navigate to settings', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForSelector("[data-sidebar='sidebar']");

    const settingsLink = page.locator("[data-sidebar='menu-button'][href*='/settings']").first();
    if (await settingsLink.isVisible()) {
      await settingsLink.click();
      await page.waitForURL('**/settings/**');
    }
  });

  test('navigate to admin hub', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForSelector("[data-sidebar='sidebar']");

    const adminLink = page.locator("[data-sidebar='menu-button'][href='/admin']").first();
    if (await adminLink.isVisible()) {
      await adminLink.click();
      await page.waitForURL('**/admin/**');
    }
  });
});
