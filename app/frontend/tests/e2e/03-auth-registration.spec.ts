import { test, expect } from '@playwright/test';

/**
 * Registration Flow E2E Tests
 *
 * Tests the user registration page and form validation.
 * Runs in the `public` project (no stored auth state).
 */
test.describe('Registration', () => {
  test('registration page loads', async ({ page }) => {
    await page.goto('/register');
    await expect(page.getByText('Create an account')).toBeVisible();
    await expect(page.getByLabel('Email')).toBeVisible();
  });

  test('registration form validates required fields', async ({ page }) => {
    await page.goto('/register');
    await expect(page.getByText('Create an account')).toBeVisible();

    // Try to submit empty form
    await page.getByRole('button', { name: /create account/i }).click();

    // Should show validation errors - form stays visible
    await expect(page.getByLabel('Email')).toBeVisible();
  });

  test('registration form validates email format', async ({ page }) => {
    await page.goto('/register');
    await expect(page.getByText('Create an account')).toBeVisible();

    await page.getByLabel('Email').fill('not-an-email');
    await page.getByRole('button', { name: /create account/i }).click();

    // Should stay on registration page with validation
    await expect(page.getByLabel('Email')).toBeVisible();
  });

  test('login link navigates to login page', async ({ page }) => {
    await page.goto('/register');

    const loginLink = page.getByRole('link', { name: /sign in/i });
    await expect(loginLink).toBeVisible();
    await loginLink.click();
    await page.waitForURL('**/login**');
  });
});
