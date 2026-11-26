import { test, expect } from './fixtures/auth';
import { navigateTo, waitForTableLoad, expectToast } from './fixtures/helpers';

/**
 * Platform Admin - Feature Flags CRUD + System Config Pages
 */
const FLAG_KEY = `e2e_flag_${Date.now()}`;
const FLAG_NAME = 'E2E Test Flag';

test.describe('Platform Admin - Feature Flags CRUD', () => {
  test('feature flags page loads', async ({ page }) => {
    await navigateTo(page, '/platform-admin/feature-flags');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('create feature flag — full workflow', async ({ page }) => {
    await navigateTo(page, '/platform-admin/feature-flags');
    await page.waitForTimeout(1_000);

    await page.getByRole('button', { name: /create feature flag/i }).click();
    await expect(page.locator('[role="dialog"]')).toBeVisible();

    await page.getByLabel('Key').fill(FLAG_KEY);
    await page.getByLabel('Name').fill(FLAG_NAME);
    const descField = page.getByLabel('Description');
    if (await descField.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await descField.fill('Created by e2e test suite');
    }

    await page.locator('[role="dialog"]').getByRole('button', { name: /save|create/i }).first().click();
    await expectToast(page, /created successfully/i);
  });

  test('created feature flag appears in table', async ({ page }) => {
    await navigateTo(page, '/platform-admin/feature-flags');
    await waitForTableLoad(page);

    await expect(page.locator('tr', { hasText: FLAG_KEY }).first()).toBeVisible();
  });

  test('edit feature flag via row action', async ({ page }) => {
    await navigateTo(page, '/platform-admin/feature-flags');
    await waitForTableLoad(page);

    const row = page.locator('tr', { hasText: FLAG_KEY }).first();
    await row.locator('button').last().click(); // "..." menu
    await page.getByRole('menuitem', { name: /edit/i }).click();
    await expect(page.locator('[role="dialog"]')).toBeVisible();

    // Edit name
    await page.getByLabel('Name').clear();
    await page.getByLabel('Name').fill(`${FLAG_NAME} Updated`);

    await page.locator('[role="dialog"]').getByRole('button', { name: /save/i }).click();
    await expectToast(page, /updated successfully/i);
  });

  test('delete feature flag via row action', async ({ page }) => {
    await navigateTo(page, '/platform-admin/feature-flags');
    await waitForTableLoad(page);

    const row = page.locator('tr', { hasText: FLAG_KEY }).first();
    if (!(await row.isVisible({ timeout: 3_000 }).catch(() => false))) return;

    await row.locator('button').last().click();
    await page.getByRole('menuitem', { name: /delete/i }).click();

    await expect(page.locator('[role="alertdialog"]')).toBeVisible();
    await page.locator('[role="alertdialog"]').getByRole('button', { name: /delete/i }).click();
    await expectToast(page, /deleted successfully/i);
  });

  test('create feature flag — validation rejects invalid key', async ({ page }) => {
    await navigateTo(page, '/platform-admin/feature-flags');
    await page.waitForTimeout(1_000);

    await page.getByRole('button', { name: /create feature flag/i }).click();
    await expect(page.locator('[role="dialog"]')).toBeVisible();

    await page.getByLabel('Key').fill('INVALID KEY FORMAT!');
    await page.getByLabel('Name').fill('Test');
    await page.locator('[role="dialog"]').getByRole('button', { name: /save|create/i }).first().click();

    await page.waitForTimeout(1_000);
    await expect(page.locator('[role="dialog"]')).toBeVisible();
  });
});

test.describe('Platform Admin - System Pages', () => {
  test('maintenance settings page loads', async ({ page }) => {
    await navigateTo(page, '/platform-admin/maintenance');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('system config page loads', async ({ page }) => {
    await navigateTo(page, '/platform-admin/system-config');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('API rate limits page loads', async ({ page }) => {
    await navigateTo(page, '/platform-admin/api-key-rate-limits');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});

test.describe('Platform Admin - Help Center Admin', () => {
  test('help center admin hub loads', async ({ page }) => {
    await navigateTo(page, '/platform-admin/help-center');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('help articles admin page loads', async ({ page }) => {
    await navigateTo(page, '/platform-admin/help-center/articles');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('help FAQs admin page loads', async ({ page }) => {
    await navigateTo(page, '/platform-admin/help-center/faqs');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('help categories admin page loads', async ({ page }) => {
    await navigateTo(page, '/platform-admin/help-center/categories');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});
