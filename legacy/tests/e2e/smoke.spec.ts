/**
 * E2E: Health and navigation smoke test
 *
 * A fast "is everything wired up?" check that runs before the heavier flow tests.
 *
 * Prerequisites: backend running at http://localhost:8000
 *                frontend running at http://localhost:5173
 */
import { test, expect } from '@playwright/test';

const API = 'http://localhost:8000';

test.describe('Smoke — health & navigation', () => {
  test('GET /api/health returns 200 with status field', async ({ page }) => {
    const resp = await page.request.get(`${API}/api/health`);
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json() as { status: string };
    expect(['ready', 'degraded']).toContain(body.status);
  });

  test('frontend root loads without JS errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    expect(errors).toHaveLength(0);
  });

  test('navigation to /docs renders document browser', async ({ page }) => {
    await page.goto('/docs');
    await page.waitForLoadState('networkidle');
    // Should stay on /docs (not redirect away)
    await expect(page).toHaveURL(/\/docs/, { timeout: 5_000 });
  });

  test('navigation to /search renders search screen', async ({ page }) => {
    await page.goto('/search');
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/search/, { timeout: 5_000 });
    // Search input should be visible
    const searchInput = page.locator('input[type="search"], input[placeholder*="search" i], [data-testid="search-input"]').first();
    await expect(searchInput).toBeVisible({ timeout: 10_000 });
  });

  test('navigation to /graph renders graph screen', async ({ page }) => {
    await page.goto('/graph');
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/graph/, { timeout: 5_000 });
  });

  test('navigation to /stats renders stats screen', async ({ page }) => {
    await page.goto('/stats');
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/stats/, { timeout: 5_000 });
    // Stats page should have at least one stat card
    const statCard = page.locator('[data-testid="stat-card"], .stat-card, h2, h3').first();
    await expect(statCard).toBeVisible({ timeout: 10_000 });
  });

  test('keyboard shortcut Ctrl+/ opens command palette', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.keyboard.press('Control+/')
    const palette = page.locator('[data-testid="command-palette"], [role="dialog"] input[type="text"]').first();
    await expect(palette).toBeVisible({ timeout: 5_000 });
    // Dismiss
    await page.keyboard.press('Escape');
  });

  test('topbar health indicator is visible', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    // Health indicator is a coloured dot/badge in the topbar
    const indicator = page.locator('[data-testid="health-indicator"], [data-status]').first();
    await expect(indicator).toBeVisible({ timeout: 15_000 });
  });
});
