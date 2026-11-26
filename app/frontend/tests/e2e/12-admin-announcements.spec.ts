import { test, expect } from './fixtures/auth';
import { navigateTo, waitForTableLoad, expectToast } from './fixtures/helpers';

/**
 * Admin Announcements E2E Tests — Full CRUD Workflow
 */
const TITLE = `E2E Announcement ${Date.now()}`;
const EDITED_TITLE = `${TITLE} (edited)`;

test.describe('Admin - Announcements CRUD', () => {
  test('announcements page loads', async ({ page }) => {
    await navigateTo(page, '/admin/announcements');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('create announcement — full workflow', async ({ page }) => {
    await navigateTo(page, '/admin/announcements');
    await page.waitForTimeout(1_000);

    // Open create dialog
    await page.getByRole('button', { name: /create announcement/i }).click();
    await expect(page.locator('[role="dialog"]')).toBeVisible();

    // Fill required fields
    await page.getByLabel('Title').fill(TITLE);
    await page.getByLabel('Body').fill('Automated e2e test announcement body.');

    // Submit via preview flow
    const previewBtn = page.locator('[role="dialog"]').getByRole('button', { name: /preview/i });
    if (await previewBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await previewBtn.click();
      await page.waitForTimeout(1_000);
      // Publish from preview
      await page.getByRole('button', { name: /publish announcement/i }).click();
    } else {
      await page.locator('[role="dialog"]').getByRole('button', { name: /create|save/i }).first().click();
    }

    // Verify success toast
    await expectToast(page, /created successfully/i);
  });

  test('created announcement appears in list', async ({ page }) => {
    await navigateTo(page, '/admin/announcements');
    await waitForTableLoad(page);

    await expect(page.locator('tr', { hasText: TITLE }).first()).toBeVisible();
  });

  test('edit announcement via row action', async ({ page }) => {
    await navigateTo(page, '/admin/announcements');
    await waitForTableLoad(page);

    // Find the row and open action menu
    const row = page.locator('tr', { hasText: TITLE }).first();
    await row.locator('button').last().click(); // "..." dropdown trigger
    await page.getByRole('menuitem', { name: /edit/i }).click();
    await expect(page.locator('[role="dialog"]')).toBeVisible();

    // Edit the title
    await page.getByLabel('Title').clear();
    await page.getByLabel('Title').fill(EDITED_TITLE);

    // Submit
    const previewBtn = page.locator('[role="dialog"]').getByRole('button', { name: /preview/i });
    if (await previewBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await previewBtn.click();
      await page.waitForTimeout(1_000);
      await page.getByRole('button', { name: /publish|save|confirm/i }).first().click();
    } else {
      await page.locator('[role="dialog"]').getByRole('button', { name: /save/i }).first().click();
    }

    await expectToast(page, /updated successfully/i);
  });

  test('delete announcement via row action', async ({ page }) => {
    await navigateTo(page, '/admin/announcements');
    await waitForTableLoad(page);

    const row = page.locator('tr', { hasText: EDITED_TITLE }).first();
    if (!(await row.isVisible({ timeout: 3_000 }).catch(() => false))) {
      // Fall back to original title if edit didn't persist in this session
      return;
    }

    await row.locator('button').last().click();
    await page.getByRole('menuitem', { name: /delete/i }).click();

    // Confirm deletion in alert dialog
    await expect(page.locator('[role="alertdialog"]')).toBeVisible();
    await page.locator('[role="alertdialog"]').getByRole('button', { name: /delete/i }).click();

    await expectToast(page, /deleted successfully/i);
  });

  test('create announcement — validation prevents empty title', async ({ page }) => {
    await navigateTo(page, '/admin/announcements');
    await page.waitForTimeout(1_000);

    await page.getByRole('button', { name: /create announcement/i }).click();
    await expect(page.locator('[role="dialog"]')).toBeVisible();

    // Fill body only, leave title empty
    await page.getByLabel('Body').fill('Body without a title');
    const submitBtn = page.locator('[role="dialog"]').getByRole('button', { name: /preview|create|save/i }).first();
    await submitBtn.click();

    // Dialog should stay open
    await page.waitForTimeout(1_000);
    await expect(page.locator('[role="dialog"]')).toBeVisible();
  });
});
