import { type Page, expect } from '@playwright/test';

// E2E_API_URL is set by playwright.config.ts at config load time.
// Fallback matches the Playwright config default (port 8100, no /api/v1 suffix).
const API_BASE = process.env.E2E_API_URL || 'http://localhost:8100';
const API_V1 = `${API_BASE}/api/v1`;

/**
 * Make an authenticated API call directly (bypass UI for setup/teardown).
 */
export async function apiCall(
  token: string,
  method: string,
  path: string,
  body?: Record<string, unknown>,
): Promise<unknown> {
  const url = `${API_V1}${path}`;
  const res = await fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${method} ${path} failed (${res.status}): ${text}`);
  }

  const contentType = res.headers.get('content-type');
  if (contentType?.includes('application/json')) {
    return res.json();
  }
  return {};
}

/**
 * Wait for a toast notification with specific text.
 */
export async function expectToast(page: Page, text: string | RegExp): Promise<void> {
  const toast = page.locator('[data-sonner-toast]', { hasText: text }).first();
  await expect(toast).toBeVisible({ timeout: 10_000 });
}

/**
 * Click a table row containing the given text.
 */
export async function clickTableRow(page: Page, text: string): Promise<void> {
  await page.locator('tr', { hasText: text }).first().click();
}

/**
 * Wait for the data table to finish loading.
 */
export async function waitForTableLoad(page: Page): Promise<void> {
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(500);
}

/**
 * Fill a select/combobox trigger by clicking it and selecting an option.
 * Works with shadcn/ui Select components.
 */
export async function selectOption(
  page: Page,
  triggerSelector: string,
  optionText: string,
): Promise<void> {
  await page.locator(triggerSelector).click();
  await page.locator('[role="option"]', { hasText: optionText }).first().click();
}

/**
 * Navigate to a page and wait for it to load.
 */
export async function navigateTo(page: Page, path: string): Promise<void> {
  await page.goto(path);
  await page.waitForLoadState('networkidle');
}

/**
 * Get the current count of table rows (excluding header).
 */
export async function getTableRowCount(page: Page): Promise<number> {
  return page.locator('tbody tr').count();
}

/**
 * Open a dialog by clicking a button with the given text.
 */
export async function openDialog(page: Page, buttonText: string): Promise<void> {
  await page.getByRole('button', { name: buttonText }).click();
  await expect(page.locator('[role="dialog"]')).toBeVisible();
}

/**
 * Click the dialog submit button. Create dialogs use "Create", edit dialogs use "Save".
 */
export async function submitDialog(page: Page): Promise<void> {
  const dialog = page.locator('[role="dialog"]');
  const createBtn = dialog.getByRole('button', { name: 'Create' });
  const saveBtn = dialog.getByRole('button', { name: 'Save' });

  if (await createBtn.isVisible({ timeout: 1_000 }).catch(() => false)) {
    await createBtn.click();
  } else {
    await saveBtn.click();
  }
}

/**
 * Confirm an alert dialog by clicking the action button.
 */
export async function confirmDialog(page: Page, buttonText = 'Confirm'): Promise<void> {
  await page.locator('[role="alertdialog"]').getByRole('button', { name: buttonText }).click();
}

/**
 * Check that a table has at least the expected number of rows.
 */
export async function expectTableHasRows(page: Page, minRows = 1): Promise<void> {
  const count = await page.locator('tbody tr').count();
  expect(count).toBeGreaterThanOrEqual(minRows);
}

/**
 * Check that a page shows an empty state (no data) message.
 */
export async function expectEmptyState(page: Page): Promise<void> {
  const emptyIndicators = page.locator('[data-testid="empty-state"], .empty-state, :text("No data"), :text("no results"), :text("Nothing here")');
  await expect(emptyIndicators.first()).toBeVisible({ timeout: 5_000 });
}

/**
 * Fill a form field by label text.
 */
export async function fillByLabel(page: Page, label: string, value: string): Promise<void> {
  await page.getByLabel(label).fill(value);
}

/**
 * Wait for a page navigation to complete after clicking something.
 */
export async function waitForNavigation(page: Page, urlPattern: string): Promise<void> {
  await page.waitForURL(urlPattern, { timeout: 15_000 });
  await page.waitForLoadState('networkidle');
}
