import { test, expect } from '@playwright/test';

console.log('>>> sidebar-collapse.spec.ts is loaded');
const MASTER_KEY = process.env.MASTER_KEY || '12345678';

test.describe('Sidebar Collapse & Hamburger Menu', () => {
  test('TASK-009: Sidebar can be collapsed and reopened, home link works', async ({ page, request }) => {
    const loginResp = await request.post('/api/auth/login', {
      data: { master_key: MASTER_KEY }
    });
    expect(loginResp.ok()).toBeTruthy();
    const data = await loginResp.json();
    const token = data.session_token || data.token;
    expect(token).toBeTruthy();

    await page.addInitScript((t: string) => {
      window.sessionStorage.setItem('mrak_session_token', t);
    }, token);

    await page.goto('/workspace');
    await expect(page.locator('[data-testid="workspace-canvas"]')).toBeVisible();

    const sidebar = page.locator('[data-testid="sidebar"]');
    await expect(sidebar).toBeVisible();

    const closeButton = page.getByLabel('Close sidebar');
    await closeButton.click();

    await expect(sidebar).toBeHidden();
    const hamburger = page.getByLabel('Open sidebar');
    await expect(hamburger).toBeVisible();

    await hamburger.click();
    await expect(sidebar).toBeVisible();

    await closeButton.click();
    await expect(sidebar).toBeHidden();

    const homeIcon = page.getByLabel('Go to projects');
    await expect(homeIcon).toBeVisible();
    await homeIcon.click();

    await expect(page).toHaveURL('/');
    await expect(page.locator('[data-testid="main-header"]')).toBeVisible();
  });
});
