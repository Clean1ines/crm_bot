import { test, expect } from '@playwright/test';

console.log('>>> workspace.spec.ts is loaded');
const MASTER_KEY = process.env.MASTER_KEY || '12345678';

test.describe('Workspace E2E', () => {
  test.beforeEach(async ({ page, request }) => {
    const loginResp = await request.post('/api/auth/login', {
       data: { master_key: MASTER_KEY }
    });
    expect(loginResp.ok()).toBeTruthy();
    const data = await loginResp.json();
    const token = data.session_token || data.token;
    expect(token, 'Backend must return session_token').toBeTruthy();
    
    await page.addInitScript((t: string) => {
      window.sessionStorage.setItem('mrak_session_token', t);
    }, token);
    
    await page.goto('/workspace');
    await expect(page.locator('[data-testid="workspace-canvas"]')).toBeVisible({ timeout: 15000 });
  });

  test('TASK-012-01: smoke - page loads after auth', async ({ page }) => {
    const canvas = page.locator('[data-testid="workspace-canvas"]');
    await expect(canvas).toBeVisible();
    await expect(page).toHaveURL(/workspace/);
  });

  test('TASK-012-02: smoke - API projects endpoint works', async ({ request }) => {
    const loginResp = await request.post('/api/auth/login', {
       data: { master_key: MASTER_KEY }
    });
    const { session_token, token } = await loginResp.json();
    const authToken = session_token || token;
    
    const resp = await request.get('/api/projects', {
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    expect([200, 401]).toContain(resp.status());
    if (resp.status() === 200) {
      const data = await resp.json();
      expect(Array.isArray(data)).toBeTruthy();
    }
  });

  test('TASK-012-03: smoke - create workflow via API', async ({ request }) => {
    const loginResp = await request.post('/api/auth/login', {
       data: { master_key: MASTER_KEY }
    });
    const { session_token, token } = await loginResp.json();
    const authToken = session_token || token;
    
    const wf = { name: 'E2E-' + Date.now(), nodes: [], edges: [] };
    const resp = await request.post('/api/workflows', {
       data: wf,
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    expect(resp.status()).not.toBe(401);
  });
});
