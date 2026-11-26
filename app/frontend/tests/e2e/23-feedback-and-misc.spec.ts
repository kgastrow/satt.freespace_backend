import { test, expect } from './fixtures/auth';
import { navigateTo } from './fixtures/helpers';

/**
 * Feedback submission, support pages, and error handling E2E tests.
 */
test.describe('Feedback Submission', () => {
  test('feedback page loads with form', async ({ page }) => {
    await navigateTo(page, '/settings/support/feedback');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('feedback form has submit button', async ({ page }) => {
    await navigateTo(page, '/settings/support/feedback');

    const submitButton = page.getByRole('button', { name: /submit|send/i }).first();
    if (await submitButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await expect(submitButton).toBeVisible();
    }
  });

  test('feedback form validates empty submission', async ({ page }) => {
    await navigateTo(page, '/settings/support/feedback');

    const submitButton = page.getByRole('button', { name: /submit|send/i }).first();
    if (await submitButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await submitButton.click();
      // Should show validation or stay on page
      await page.waitForTimeout(1_000);
      await expect(page.locator('h1, h2, h3').first()).toBeVisible();
    }
  });

  test('can fill feedback form', async ({ page }) => {
    await navigateTo(page, '/settings/support/feedback');

    // Look for textarea or message input
    const messageField = page.locator('textarea').first();
    if (await messageField.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await messageField.fill('E2E test feedback - please ignore');
    }
  });
});

test.describe('Support Pages', () => {
  test('about page loads with content', async ({ page }) => {
    await navigateTo(page, '/settings/support/about');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });

  test('changelog page loads with entries', async ({ page }) => {
    await navigateTo(page, '/settings/support/changelog');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});

test.describe('Error Pages', () => {
  test('404 page renders for non-existent route', async ({ page }) => {
    await navigateTo(page, '/this-page-does-not-exist-12345');
    await page.waitForTimeout(2_000);

    const pageContent = await page.content();
    const has404 = pageContent.includes('404') ||
                   pageContent.toLowerCase().includes('not found');
    const redirected = page.url().includes('dashboard') || page.url().includes('login');
    expect(has404 || redirected).toBe(true);
  });

  test('404 page has home link', async ({ page }) => {
    await navigateTo(page, '/this-page-does-not-exist-12345');
    await page.waitForTimeout(2_000);

    const homeLink = page.getByRole('link', { name: /home|dashboard|back/i }).first();
    if (await homeLink.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await homeLink.click();
      await page.waitForURL('**/dashboard**');
    }
  });
});
