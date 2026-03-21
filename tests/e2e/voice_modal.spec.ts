/**
 * E2E: Voice modal – open and dismiss without recording
 *
 * Prerequisites: backend running at http://localhost:8000
 *                frontend running at http://localhost:5173
 *
 * Note: actual recording is not tested in E2E because Playwright headless
 * mode does not expose real microphone hardware. The dismiss flow is
 * verifiable without a real device.
 */
import { test, expect } from '@playwright/test';

test.describe('Voice modal', () => {
  test.beforeEach(async ({ page }) => {
    // Grant fake microphone permission so the modal does not block on permission prompt
    await page.context().grantPermissions(['microphone']);
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('microphone button opens the voice modal', async ({ page }) => {
    const micBtn = page.locator('[data-testid="mic-btn"], button[aria-label*="voice" i], button[aria-label*="mic" i]').first();
    await expect(micBtn).toBeVisible({ timeout: 10_000 });
    await micBtn.click();

    // Voice modal should appear
    const modal = page.locator('[data-testid="voice-modal"], [role="dialog"]').first();
    await expect(modal).toBeVisible({ timeout: 5_000 });
  });

  test('voice modal closes when Cancel is clicked', async ({ page }) => {
    const micBtn = page.locator('[data-testid="mic-btn"], button[aria-label*="voice" i], button[aria-label*="mic" i]').first();
    await expect(micBtn).toBeVisible({ timeout: 10_000 });
    await micBtn.click();

    const modal = page.locator('[data-testid="voice-modal"], [role="dialog"]').first();
    await expect(modal).toBeVisible({ timeout: 5_000 });

    // Click Cancel button inside the modal
    const cancelBtn = modal.locator('button:has-text("Cancel"), button:has-text("Close"), [data-testid="voice-cancel"]').first();
    await expect(cancelBtn).toBeVisible({ timeout: 5_000 });
    await cancelBtn.click();

    await expect(modal).not.toBeVisible({ timeout: 5_000 });
  });

  test('voice modal closes with Escape key', async ({ page }) => {
    const micBtn = page.locator('[data-testid="mic-btn"], button[aria-label*="voice" i], button[aria-label*="mic" i]').first();
    await expect(micBtn).toBeVisible({ timeout: 10_000 });
    await micBtn.click();

    const modal = page.locator('[data-testid="voice-modal"], [role="dialog"]').first();
    await expect(modal).toBeVisible({ timeout: 5_000 });

    await page.keyboard.press('Escape');
    await expect(modal).not.toBeVisible({ timeout: 5_000 });
  });
});
