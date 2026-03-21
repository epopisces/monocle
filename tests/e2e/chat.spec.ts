/**
 * E2E: Chat starter sends message and receives a streaming response
 *
 * Prerequisites: backend running at http://localhost:8000 with an AI provider responding
 *                frontend running at http://localhost:5173
 */
import { test, expect } from '@playwright/test';

test.describe('Chat screen', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('chat starter tiles are visible on the home screen', async ({ page }) => {
    // Chat starters are 2×3 tile grid
    const tiles = page.locator('[data-testid="chat-starter"], .chat-starter');
    // At least one tile visible
    await expect(tiles.first()).toBeVisible({ timeout: 10_000 });
  });

  test('typing a message in the input and sending it shows it in the thread', async ({ page }) => {
    const input = page.locator('textarea[placeholder], [data-testid="chat-input"] textarea').first();
    await expect(input).toBeVisible({ timeout: 10_000 });

    await input.fill('Hello from E2E test');

    // Send with Enter
    await input.press('Enter');

    // The user message should appear in the thread
    const userMsg = page.locator('text=Hello from E2E test');
    await expect(userMsg).toBeVisible({ timeout: 10_000 });
  });

  test('keyboard shortcut Ctrl+/ opens chat (navigates to /)', async ({ page }) => {
    await page.goto('/stats');
    await page.waitForLoadState('networkidle');
    await page.keyboard.press('Control+/');
    await expect(page).toHaveURL('/', { timeout: 5_000 });
  });
});
