import { test, expect } from './fixtures/auth';
import { navigateTo, waitForTableLoad } from './fixtures/helpers';

/**
 * Admin User Management E2E Tests
 *
 * Tests user listing, invitation, detail view, and management.
 * Note: User creation in this app is via invitation (email only), not a full form.
 */
test.describe('Admin - User Management', () => {
  test('users list page loads with table', async ({ page }) => {
    await navigateTo(page, '/admin/users');
    await waitForTableLoad(page);

    const table = page.locator('table');
    await expect(table).toBeVisible();
    const rows = page.locator('tbody tr');
    expect(await rows.count()).toBeGreaterThanOrEqual(1);
  });

  test('users table shows smoke test user', async ({ page }) => {
    await navigateTo(page, '/admin/users');
    await waitForTableLoad(page);

    const row = page.locator('tr', { hasText: /smoke/i }).first();
    await expect(row).toBeVisible();
  });

  test('invite user dialog opens and validates', async ({ page }) => {
    await navigateTo(page, '/admin/users');
    await waitForTableLoad(page);

    // Open invite dialog
    await page.getByRole('button', { name: /invite|create|add|new/i }).first().click();
    await expect(page.locator('[role="dialog"]')).toBeVisible();

    // Try to submit without email
    await page.locator('[role="dialog"]').getByRole('button', { name: /send|invite|create/i }).click();

    // Dialog should stay open (validation)
    await page.waitForTimeout(1_000);
    await expect(page.locator('[role="dialog"]')).toBeVisible();
  });

  test('invite user - fill email and submit', async ({ page }) => {
    await navigateTo(page, '/admin/users');
    await waitForTableLoad(page);

    await page.getByRole('button', { name: /invite|create|add|new/i }).first().click();
    await expect(page.locator('[role="dialog"]')).toBeVisible();

    // Fill email - the input may be found by placeholder or by role
    const emailInput = page.locator('[role="dialog"] input[type="email"], [role="dialog"] input').first();
    await emailInput.fill(`e2e-invite-${Date.now()}@example.com`);

    // Submit via "Send Invitation" button
    await page.locator('[role="dialog"]').getByRole('button', { name: /send invitation|send|invite/i }).click();

    // Wait for response - dialog should close on success or show error
    await page.waitForTimeout(3_000);
  });

  test('user detail page loads', async ({ page }) => {
    await navigateTo(page, '/admin/users');
    await waitForTableLoad(page);

    // Click into user row
    const userRow = page.locator('tr', { hasText: /smoke/i }).first();
    await userRow.click();
    await page.waitForTimeout(2_000);

    await expect(page.getByText(/smoke/i).first()).toBeVisible();
  });

  test('users table has columns for key data', async ({ page }) => {
    await navigateTo(page, '/admin/users');
    await waitForTableLoad(page);

    // Check table headers exist
    const headers = page.locator('thead th');
    expect(await headers.count()).toBeGreaterThanOrEqual(3);
  });

  test('onboarding review page loads', async ({ page }) => {
    await navigateTo(page, '/admin/onboarding-review');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});
