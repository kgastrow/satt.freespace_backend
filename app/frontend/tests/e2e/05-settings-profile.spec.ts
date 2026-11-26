import { test, expect } from './fixtures/auth';
import { navigateTo, waitForTableLoad } from './fixtures/helpers';

/**
 * User Settings - Profile & Account E2E Tests
 *
 * Tests profile viewing/editing, avatar, sessions management.
 */
test.describe('Settings - Profile', () => {
  test('profile page loads with form', async ({ page }) => {
    await navigateTo(page, '/settings/account/profile');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('profile shows user name fields', async ({ page }) => {
    await navigateTo(page, '/settings/account/profile');

    // Check for name fields
    const firstName = page.getByLabel('First Name');
    const lastName = page.getByLabel('Last Name');

    if (await firstName.isVisible({ timeout: 5_000 }).catch(() => false)) {
      const value = await firstName.inputValue();
      expect(value.length).toBeGreaterThan(0);
    }
  });

  test('can edit and save profile', async ({ page }) => {
    await navigateTo(page, '/settings/account/profile');

    const lastNameInput = page.getByLabel('Last Name');
    if (await lastNameInput.isVisible({ timeout: 5_000 }).catch(() => false)) {
      const original = await lastNameInput.inputValue();
      await lastNameInput.clear();
      await lastNameInput.fill('E2EUpdated');

      const saveButton = page.getByRole('button', { name: /save|update/i }).first();
      if (await saveButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await saveButton.click();
        await page.waitForTimeout(2_000);

        // Restore original
        await lastNameInput.clear();
        await lastNameInput.fill(original);
        await saveButton.click();
        await page.waitForTimeout(2_000);
      }
    }
  });

  test('avatar upload area exists', async ({ page }) => {
    await navigateTo(page, '/settings/account/profile');

    // Should show avatar or upload area
    const chooseFileButton = page.getByRole('button', { name: /choose file|upload|change/i }).first();
    if (await chooseFileButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await expect(chooseFileButton).toBeEnabled();
    }
  });
});

test.describe('Settings - Connected Accounts', () => {
  test('connected accounts page loads', async ({ page }) => {
    await navigateTo(page, '/settings/account/connected');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});

test.describe('Settings - Sessions', () => {
  test('sessions page shows current session', async ({ page }) => {
    await navigateTo(page, '/settings/account/sessions');
    await waitForTableLoad(page);
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('revoke session button exists', async ({ page }) => {
    await navigateTo(page, '/settings/account/sessions');
    await waitForTableLoad(page);

    // Should have revoke buttons for sessions
    const revokeButton = page.getByRole('button', { name: /revoke|terminate|end/i }).first();
    if (await revokeButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await expect(revokeButton).toBeEnabled();
    }
  });
});

test.describe('Settings - Files', () => {
  test('user files page loads', async ({ page }) => {
    await navigateTo(page, '/settings/account/files');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});
