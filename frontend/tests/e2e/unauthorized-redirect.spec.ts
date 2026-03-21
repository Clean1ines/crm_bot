import { test, expect } from '@playwright/test';

console.log('>>> unauthorized-redirect.spec.ts is loaded');

const MASTER_KEY = process.env.MASTER_KEY || '12345678';

test.describe('401 Unauthorized Redirect', () => {
  test('should redirect to /login when API returns 401', async ({ page, request }) => {
    // Login via API to get token
    const loginResp = await request.post('/api/auth/login', {
      data: { master_key: MASTER_KEY }
    });
    expect(loginResp.ok()).toBeTruthy();
    const data = await loginResp.json();
    const token = data.session_token || data.token;
    expect(token).toBeTruthy();

    // Set token in sessionStorage for browser
    await page.addInitScript((t: string) => {
      window.sessionStorage.setItem('mrak_session_token', t);
    }, token);

    // Setup route to intercept /api/projects and return 401
    await page.route('**/api/projects', (route) => {
      console.log('Intercepted /api/projects, returning 401');
      route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Unauthorized' })
      });
    });

    // Navigate to workspace
    await page.goto('/workspace');

    // Wait for redirect to login page
    await expect(page).toHaveURL('/login', { timeout: 10000 });
  });
});
