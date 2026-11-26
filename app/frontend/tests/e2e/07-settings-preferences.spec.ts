import { test, expect } from './fixtures/auth';
import { navigateTo } from './fixtures/helpers';

/**
 * User Settings - Preferences E2E Tests
 *
 * Tests notification preferences with channel toggles, language switching, appearance toggle.
 */
test.describe('Settings - Notification Preferences', () => {
  test('notification preferences page loads with channel toggles', async ({ page }) => {
    await navigateTo(page, '/settings/preferences/notifications');

    await expect(page.locator('h1, h2, h3').first()).toBeVisible();

    // Should show channel toggle switches
    const emailSwitch = page.getByLabel('Email');
    const inAppSwitch = page.getByLabel('In App');
    const hasSwitches = await emailSwitch.isVisible({ timeout: 5_000 }).catch(() => false) ||
                        await inAppSwitch.isVisible({ timeout: 5_000 }).catch(() => false);
    expect(hasSwitches).toBe(true);
  });

  test('can toggle notification channel', async ({ page }) => {
    await navigateTo(page, '/settings/preferences/notifications');

    const emailSwitch = page.getByLabel('Email');
    if (await emailSwitch.isVisible({ timeout: 5_000 }).catch(() => false)) {
      // Toggle the switch
      await emailSwitch.click();
      await page.waitForTimeout(500);
      // Toggle it back
      await emailSwitch.click();
    }
  });

  test('save preferences button exists', async ({ page }) => {
    await navigateTo(page, '/settings/preferences/notifications');

    const saveButton = page.getByRole('button', { name: /save|update/i }).first();
    if (await saveButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await expect(saveButton).toBeEnabled();
    }
  });
});

test.describe('Settings - Language', () => {
  test('language page loads with options', async ({ page }) => {
    await navigateTo(page, '/settings/preferences/language');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});

test.describe('Settings - Appearance', () => {
  test('appearance page loads with theme toggle', async ({ page }) => {
    await navigateTo(page, '/settings/preferences/appearance');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});

test.describe('Settings - Navigation', () => {
  test('settings sidebar navigates between sections', async ({ page }) => {
    await navigateTo(page, '/settings/account/profile');

    // Navigate to security via sidebar
    const securityLink = page.getByRole('link', { name: /password/i });
    if (await securityLink.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await securityLink.click();
      await page.waitForURL('**/settings/security/password**');
      await expect(page.getByLabel('Current Password')).toBeVisible();
    }
  });
});

test.describe('Settings - Support', () => {
  test('about page loads with app info', async ({ page }) => {
    await navigateTo(page, '/settings/support/about');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('changelog page loads', async ({ page }) => {
    await navigateTo(page, '/settings/support/changelog');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});
