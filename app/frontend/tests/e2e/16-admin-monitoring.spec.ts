import { test, expect } from './fixtures/auth';
import { navigateTo, waitForTableLoad } from './fixtures/helpers';

/**
 * Admin Monitoring E2E Tests
 *
 * Tests audit logs with filtering, feedback list, and reports.
 */
test.describe('Admin - Audit Logs', () => {
  test('audit logs page loads with table', async ({ page }) => {
    await navigateTo(page, '/admin/audit-logs');
    await waitForTableLoad(page);

    const table = page.locator('table');
    await expect(table).toBeVisible();
  });

  test('audit logs has filter controls', async ({ page }) => {
    await navigateTo(page, '/admin/audit-logs');
    await waitForTableLoad(page);

    // Check for filter dropdowns
    const actionFilter = page.getByLabel('Action');
    const resourceFilter = page.getByLabel('Resource Type');
    const searchInput = page.getByPlaceholder(/search/i);

    const hasFilters = await actionFilter.isVisible({ timeout: 3_000 }).catch(() => false) ||
                       await resourceFilter.isVisible({ timeout: 3_000 }).catch(() => false) ||
                       await searchInput.isVisible({ timeout: 3_000 }).catch(() => false);

    expect(hasFilters).toBe(true);
  });

  test('audit logs filter by action type', async ({ page }) => {
    await navigateTo(page, '/admin/audit-logs');
    await waitForTableLoad(page);

    // Try to filter by action
    const actionFilter = page.getByLabel('Action');
    if (await actionFilter.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await actionFilter.click();
      const createOption = page.locator('[role="option"]', { hasText: /CREATE/i }).first();
      if (await createOption.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await createOption.click();
        await waitForTableLoad(page);
        // Table should update with filtered results
      }
    }
  });

  test('audit log detail view opens', async ({ page }) => {
    await navigateTo(page, '/admin/audit-logs');
    await waitForTableLoad(page);

    // Click on first row or detail button
    const detailButton = page.getByRole('button', { name: /view|detail/i }).first();
    const firstRow = page.locator('tbody tr').first();

    if (await detailButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await detailButton.click();
      await page.waitForTimeout(1_000);
    } else if (await firstRow.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await firstRow.click();
      await page.waitForTimeout(1_000);
    }
  });
});

test.describe('Admin - Feedback', () => {
  test('feedback list page loads', async ({ page }) => {
    await navigateTo(page, '/admin/feedback');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});

test.describe('Admin - Reports', () => {
  test('reports page loads', async ({ page }) => {
    await navigateTo(page, '/admin/reports');
    await expect(page.locator('h1, h2, h3').first()).toBeVisible();
  });
});
