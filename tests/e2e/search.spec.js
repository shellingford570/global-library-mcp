const { test, expect } = require('@playwright/test');

test('search UI renders evidence cards from the API', async ({ page }) => {
  await page.route('**/api/search**', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        query: 'railway',
        results: [{
          library_id: 'ndl',
          library_name: 'National Diet Library',
          title: 'Railway evidence record',
          author: 'Test author',
          description: 'OCR evidence snippet',
          landing_url: 'https://example.test/item/1',
          rights: { statement: 'verify at item level' },
        }],
        errors: [],
      }),
    });
  });

  await page.goto('/');
  await expect(page.getByText('Global Library MCP')).toBeVisible();
  await page.locator('#query').fill('railway');
  await page.getByRole('button', { name: '検索する' }).click();
  await expect(page.getByText('Railway evidence record')).toBeVisible();
  await expect(page.getByText('OCR evidence snippet')).toBeVisible();
  await expect(page.getByRole('link', { name: /原本へ戻る/ })).toHaveAttribute('href', 'https://example.test/item/1');
});

test('AI answer remains explicit when the provider is unavailable', async ({ page }) => {
  await page.route('**/api/answer**', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ available: false, reason: 'LLM is disabled', search: { results: [] } }),
    });
  });

  await page.goto('/');
  await page.locator('#query').fill('発電');
  await page.getByRole('button', { name: 'AI回答' }).click();
  await expect(page.getByText(/AI回答は利用できません/)).toBeVisible();
});
