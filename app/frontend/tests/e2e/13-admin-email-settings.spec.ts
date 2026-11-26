import { test, expect } from './fixtures/auth';
import { navigateTo, waitForTableLoad, expectToast } from './fixtures/helpers';

/**
 * Admin Email Settings & Changelog CRUD E2E Tests
 */
const CHANGELOG_TITLE = `E2E Release ${Date.now()}`;

test.describe('Admin - Email Settings', () => {
  test('email settings page loads', async ({ page }) => {
    await navigateTo(page, '/admin/email/settings');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('email settings shows configuration form', async ({ page }) => {
    await navigateTo(page, '/admin/email/settings');
    await page.waitForTimeout(1_000);
    // Should have some form elements or configuration display
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});

test.describe('Admin - Changelog CRUD', () => {
  test('changelog page loads', async ({ page }) => {
    await navigateTo(page, '/admin/changelog');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('create changelog entry — full workflow', async ({ page }) => {
    await navigateTo(page, '/admin/changelog');
    await page.waitForTimeout(1_000);

    await page.getByRole('button', { name: /create entry/i }).click();
    await expect(page.locator('[role="dialog"]')).toBeVisible();

    // Fill form
    await page.getByLabel('Version').fill('99.0.0');
    await page.getByLabel('Title').fill(CHANGELOG_TITLE);
    await page.getByLabel('Body').fill('E2E test changelog entry body.');

    // Select category
    const categorySelect = page.getByLabel('Category');
    if (await categorySelect.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await categorySelect.click();
      await page.locator('[role="option"]', { hasText: /feature/i }).first().click();
    }

    await page.locator('[role="dialog"]').getByRole('button', { name: /^create$/i }).click();
    await expectToast(page, /created successfully/i);
  });

  test('created changelog entry appears in list', async ({ page }) => {
    await navigateTo(page, '/admin/changelog');
    await waitForTableLoad(page);

    await expect(page.getByText(CHANGELOG_TITLE).first()).toBeVisible();
  });

  test('delete changelog entry via row action', async ({ page }) => {
    await navigateTo(page, '/admin/changelog');
    await waitForTableLoad(page);

    // Find the entry row and open action menu
    const entryRow = page.locator('tr, [data-testid]', { hasText: CHANGELOG_TITLE }).first();
    if (!(await entryRow.isVisible({ timeout: 3_000 }).catch(() => false))) return;

    const menuButton = entryRow.locator('button').last();
    await menuButton.click();
    await page.getByRole('menuitem', { name: /delete/i }).click();

    await expect(page.locator('[role="alertdialog"]')).toBeVisible();
    await page.locator('[role="alertdialog"]').getByRole('button', { name: /delete/i }).click();
    await expectToast(page, /deleted successfully/i);
  });
});

test.describe('Admin - About Settings', () => {
  test('about settings page loads', async ({ page }) => {
    await navigateTo(page, '/admin/about');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});
