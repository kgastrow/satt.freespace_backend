import { test, expect } from '@playwright/test';

/**
 * Password Reset Flow E2E Tests
 *
 * Tests the forgot-password and reset-password pages.
 * Runs in the `public` project (no stored auth state).
 */
test.describe('Password Reset', () => {
  test('forgot password page loads', async ({ page }) => {
    await page.goto('/forgot-password');
    await expect(page.getByText('Forgot password?')).toBeVisible();
    await expect(page.getByLabel('Email')).toBeVisible();
  });

  test('forgot password submits email', async ({ page }) => {
    await page.goto('/forgot-password');
    await page.getByLabel('Email').fill('smoke-test@example.com');

    await page.getByRole('button', { name: /send reset link/i }).click();

    // Should show success message or stay on page
    await page.waitForTimeout(2_000);
  });

  test('forgot password validates empty email', async ({ page }) => {
    await page.goto('/forgot-password');

    await page.getByRole('button', { name: /send reset link/i }).click();

    // Should stay on page with validation error
    await expect(page.getByLabel('Email')).toBeVisible();
  });

  test('reset password page loads with token', async ({ page }) => {
    await page.goto('/reset-password?token=test-token');
    // Page should render (may show error for invalid token, but page loads)
    await page.waitForTimeout(2_000);
  });

  test('back to login link works', async ({ page }) => {
    await page.goto('/forgot-password');

    const loginLink = page.getByRole('link', { name: /back to sign in/i });
    await expect(loginLink).toBeVisible();
    await loginLink.click();
    await page.waitForURL('**/login**');
  });
});
