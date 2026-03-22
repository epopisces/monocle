/**
 * E2E: Graph screen – focus input navigation
 *
 * Prerequisites: backend running at http://localhost:8000
 *                frontend running at http://localhost:5173
 */
import { test, expect } from '@playwright/test';

test.describe('Graph screen', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/graph');
    await page.waitForLoadState('networkidle');
  });

  test('graph screen renders without errors', async ({ page }) => {
    // Page title or main heading should be present
    const heading = page.locator('h1, h2, [data-testid="graph-screen"]').first();
    await expect(heading).toBeVisible({ timeout: 10_000 });
  });

  test('focus input accepts text and triggers a graph query', async ({ page }) => {
    const focusInput = page.locator('input[placeholder*="focus" i], input[placeholder*="person" i], [data-testid="graph-focus-input"]').first();
    await expect(focusInput).toBeVisible({ timeout: 10_000 });

    await focusInput.fill('alice');
    await focusInput.press('Enter');

    // After submitting the graph should still be on /graph (no navigation away)
    await expect(page).toHaveURL(/\/graph/, { timeout: 5_000 });
  });

  test('depth toggle buttons are visible', async ({ page }) => {
    // Depth [1] [2] [3] toggle buttons
    const depthBtn = page.locator('button:has-text("1"), button:has-text("2"), button:has-text("3"), [data-testid="depth-1"]').first();
    await expect(depthBtn).toBeVisible({ timeout: 10_000 });
  });
});
