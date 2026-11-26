import { test, expect } from './fixtures/auth';
import { navigateTo, waitForTableLoad, expectToast } from './fixtures/helpers';

/**
 * Platform Admin - Roles CRUD, Permissions, User Types
 */
const ROLE_NAME = `E2E Role ${Date.now()}`;

test.describe('Platform Admin - Roles CRUD', () => {
  test('roles page loads with list', async ({ page }) => {
    await navigateTo(page, '/platform-admin/roles');
    await waitForTableLoad(page);
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('create role — full workflow', async ({ page }) => {
    await navigateTo(page, '/platform-admin/roles');
    await page.waitForTimeout(1_000);

    await page.getByRole('button', { name: /create role/i }).click();
    await expect(page.locator('[role="dialog"]')).toBeVisible();

    await page.getByLabel('Name').fill(ROLE_NAME);
    const descField = page.getByLabel(/description/i);
    if (await descField.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await descField.fill('Created by e2e test suite');
    }

    await page.locator('[role="dialog"]').getByRole('button', { name: /^create$/i }).click();
    await expectToast(page, /created successfully/i);
  });

  test('created role appears in table', async ({ page }) => {
    await navigateTo(page, '/platform-admin/roles');
    await waitForTableLoad(page);

    await expect(page.locator('tr', { hasText: ROLE_NAME }).first()).toBeVisible();
  });

  test('edit role via row action', async ({ page }) => {
    await navigateTo(page, '/platform-admin/roles');
    await waitForTableLoad(page);

    const row = page.locator('tr', { hasText: ROLE_NAME }).first();
    await row.locator('button').last().click();
    await page.getByRole('menuitem', { name: /edit/i }).click();
    await expect(page.locator('[role="dialog"]')).toBeVisible();

    await page.getByLabel('Name').clear();
    await page.getByLabel('Name').fill(`${ROLE_NAME} Updated`);
    await page.locator('[role="dialog"]').getByRole('button', { name: /save/i }).click();
    await expectToast(page, /updated successfully/i);
  });

  test('delete role via row action', async ({ page }) => {
    await navigateTo(page, '/platform-admin/roles');
    await waitForTableLoad(page);

    const row = page.locator('tr', { hasText: ROLE_NAME }).first();
    if (!(await row.isVisible({ timeout: 3_000 }).catch(() => false))) return;

    await row.locator('button').last().click();
    await page.getByRole('menuitem', { name: /delete/i }).click();

    await expect(page.locator('[role="alertdialog"]')).toBeVisible();
    await page.locator('[role="alertdialog"]').getByRole('button', { name: /delete/i }).click();
    await expectToast(page, /deleted successfully/i);
  });
});

test.describe('Platform Admin - Permissions & User Types', () => {
  test('permissions page loads', async ({ page }) => {
    await navigateTo(page, '/platform-admin/permissions');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('user types page loads', async ({ page }) => {
    await navigateTo(page, '/platform-admin/user-types');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});
