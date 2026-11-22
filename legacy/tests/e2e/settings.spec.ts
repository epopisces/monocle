/**
 * E2E: Settings modal – open, read, patch, and verify round-trip
 *
 * Prerequisites: backend running at http://localhost:8000
 *                frontend running at http://localhost:5173
 */
import { test, expect } from '@playwright/test';

const API = 'http://localhost:8000';

test.describe('Settings round-trip', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('GET /api/settings returns expected shape with masked MCP key', async ({ page }) => {
    const resp = await page.request.get(`${API}/api/settings`);
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json() as Record<string, unknown>;

    expect(body).toHaveProperty('ai');
    expect(body).toHaveProperty('vault');
    expect(body).toHaveProperty('review');
    // MCP key must be masked — should never be the full key
    if (body.mcp_key_last4 !== undefined) {
      expect(String(body.mcp_key_last4).length).toBeLessThanOrEqual(4);
    }
  });

  test('settings modal can be opened via keyboard shortcut Ctrl+,', async ({ page }) => {
    await page.keyboard.press('Control+,');
    const modal = page.locator('[data-testid="settings-modal"], [role="dialog"]').first();
    await expect(modal).toBeVisible({ timeout: 5_000 });
  });

  test('settings modal opens from topbar and shows AI provider section', async ({ page }) => {
    // Look for a settings/gear button in the topbar
    const settingsBtn = page.locator('[data-testid="settings-btn"], button[aria-label*="settings" i], button[title*="settings" i]').first();
    await expect(settingsBtn).toBeVisible({ timeout: 10_000 });
    await settingsBtn.click();

    const modal = page.locator('[data-testid="settings-modal"], [role="dialog"]').first();
    await expect(modal).toBeVisible({ timeout: 5_000 });

    // Should contain AI provider picker or text about provider
    const aiSection = modal.locator('text=/provider|ollama|azure|foundry/i').first();
    await expect(aiSection).toBeVisible({ timeout: 5_000 });
  });

  test('settings modal closes with Escape key', async ({ page }) => {
    await page.keyboard.press('Control+,');
    const modal = page.locator('[data-testid="settings-modal"], [role="dialog"]').first();
    await expect(modal).toBeVisible({ timeout: 5_000 });

    await page.keyboard.press('Escape');
    await expect(modal).not.toBeVisible({ timeout: 5_000 });
  });

  test('PATCH /api/settings with valid payload returns 200', async ({ page }) => {
    // Read current review settings first
    const get = await page.request.get(`${API}/api/settings`);
    expect(get.ok()).toBeTruthy();
    const current = await get.json() as { review: { queue_threshold: number } };
    const originalThreshold = current.review?.queue_threshold ?? 0.6;

    // Patch to same value (idempotent round-trip)
    const patch = await page.request.patch(`${API}/api/settings`, {
      headers: { 'Content-Type': 'application/json' },
      data: { review: { queue_threshold: originalThreshold } },
    });
    expect(patch.ok()).toBeTruthy();

    // Verify the value persisted
    const verify = await page.request.get(`${API}/api/settings`);
    const verified = await verify.json() as { review: { queue_threshold: number } };
    expect(verified.review?.queue_threshold).toBe(originalThreshold);
  });
});
