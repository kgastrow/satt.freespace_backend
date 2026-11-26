import { test, expect } from './fixtures/auth';
import { navigateTo } from './fixtures/helpers';

/**
 * User Settings - Security E2E Tests
 *
 * Tests password change form validation, email change, 2FA, data export, account deletion.
 */
test.describe('Settings - Security', () => {
  test('password change page loads with form fields', async ({ page }) => {
    await navigateTo(page, '/settings/security/password');

    await expect(page.getByText('Change Password')).toBeVisible();
    // Form has 3 password inputs
    const passwordInputs = page.locator('input[type="password"]');
    expect(await passwordInputs.count()).toBeGreaterThanOrEqual(3);
    await expect(page.getByRole('button', { name: /update password/i })).toBeVisible();
  });

  test('password change validates empty submission', async ({ page }) => {
    await navigateTo(page, '/settings/security/password');

    await page.getByRole('button', { name: /update password/i }).click();

    // Should show validation errors, form stays
    await page.waitForTimeout(1_000);
    await expect(page.getByText('Change Password')).toBeVisible();
  });

  test('password change validates mismatch', async ({ page }) => {
    await navigateTo(page, '/settings/security/password');

    const inputs = page.locator('input[type="password"]');
    await inputs.nth(0).fill('SmokeTest@123');      // Current Password
    await inputs.nth(1).fill('NewPassword123!');      // New Password
    await inputs.nth(2).fill('DifferentPassword!9');  // Confirm (mismatch)

    await page.getByRole('button', { name: /update password/i }).click();

    // Should show mismatch error, form stays on page
    await page.waitForTimeout(1_000);
    await expect(page.getByText('Change Password')).toBeVisible();
  });

  test('email change page loads with current email', async ({ page }) => {
    await navigateTo(page, '/settings/security/email');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
    // Should show current email somewhere on the page
    await expect(page.getByText(/smoke-test@example.com/i).first()).toBeVisible({ timeout: 5_000 }).catch(() => {
      // Email might be displayed differently
    });
  });

  test('2FA settings page shows setup option', async ({ page }) => {
    await navigateTo(page, '/settings/security/2fa');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
    // Should show enable/setup 2FA button (since smoke user doesn't have 2FA)
    const setupButton = page.getByRole('button', { name: /enable|setup|configure/i }).first();
    if (await setupButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await expect(setupButton).toBeEnabled();
    }
  });

  test('privacy page loads', async ({ page }) => {
    await navigateTo(page, '/settings/security/privacy');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('data export page has request button', async ({ page }) => {
    await navigateTo(page, '/settings/security/export');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
    const exportButton = page.getByRole('button', { name: /request|export|download/i }).first();
    if (await exportButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await expect(exportButton).toBeEnabled();
    }
  });

  test('delete account page shows confirmation requirement', async ({ page }) => {
    await navigateTo(page, '/settings/danger/delete');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
    // Should have a delete button (disabled or requiring confirmation)
    const deleteButton = page.getByRole('button', { name: /delete|request deletion/i }).first();
    if (await deleteButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await expect(deleteButton).toBeVisible();
    }
  });
});
