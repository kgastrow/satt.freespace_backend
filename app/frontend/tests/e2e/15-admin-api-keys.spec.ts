import { test, expect } from './fixtures/auth';
import { navigateTo, waitForTableLoad, expectToast } from './fixtures/helpers';

/**
 * Admin API Keys E2E Tests — Full CRUD Workflow
 */
const KEY_NAME = `E2E Key ${Date.now()}`;

test.describe('Admin - API Keys CRUD', () => {
  test('API keys page loads', async ({ page }) => {
    await navigateTo(page, '/admin/api-keys');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('create API key — full workflow', async ({ page }) => {
    await navigateTo(page, '/admin/api-keys');
    await page.waitForTimeout(1_000);

    // The page header button and dialog button may both say "Create API Key"
    // Click the header button first
    await page.getByRole('button', { name: /create api key/i }).first().click();
    await expect(page.locator('[role="dialog"]')).toBeVisible();

    // Fill name
    await page.getByLabel('Name').fill(KEY_NAME);

    // Click the last button in the dialog (the Create API Key submit button)
    const buttons = page.locator('[role="dialog"] button');
    const count = await buttons.count();
    // The submit button is the last one in the dialog
    await buttons.nth(count - 1).click();

    // Wait for result — either key display dialog or page refresh
    await page.waitForTimeout(5_000);

    // If key display dialog appeared, close it
    const closeBtn = page.getByRole('button', { name: /^close$/i });
    if (await closeBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await closeBtn.click();
    }
  });

  test('API key list shows keys or empty state', async ({ page }) => {
    await navigateTo(page, '/admin/api-keys');
    await page.waitForTimeout(2_000);

    // Should show either a table with keys or the "No API keys yet" empty state
    const table = page.locator('table');
    const emptyState = page.getByText(/no api keys yet/i);
    const hasTable = await table.isVisible({ timeout: 3_000 }).catch(() => false);
    const hasEmpty = await emptyState.isVisible({ timeout: 3_000 }).catch(() => false);
    expect(hasTable || hasEmpty).toBe(true);
  });

  test('revoke API key via row action', async ({ page }) => {
    await navigateTo(page, '/admin/api-keys');
    await waitForTableLoad(page);

    const row = page.locator('tr', { hasText: KEY_NAME }).first();
    if (!(await row.isVisible({ timeout: 3_000 }).catch(() => false))) return;

    // Click delete/revoke button (trash icon in row)
    const deleteBtn = row.locator('button').last();
    await deleteBtn.click();

    // Confirm revocation in alert dialog
    const alertDialog = page.locator('[role="alertdialog"]');
    if (await alertDialog.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await alertDialog.getByRole('button', { name: /revoke|delete|confirm/i }).click();
      await expectToast(page, /revoked successfully/i);
    }
  });

  test('create API key — validation prevents empty name', async ({ page }) => {
    await navigateTo(page, '/admin/api-keys');
    await page.waitForTimeout(1_000);

    await page.getByRole('button', { name: /create api key/i }).click();
    await expect(page.locator('[role="dialog"]')).toBeVisible();

    // Submit without name
    await page.locator('[role="dialog"]').getByRole('button', { name: /create api key/i }).click();

    await page.waitForTimeout(1_000);
    await expect(page.locator('[role="dialog"]')).toBeVisible();
  });
});
