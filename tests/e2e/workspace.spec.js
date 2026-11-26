// b7: Research Workspace journeys. These run only against a
// workspace-enabled server (meta glm-workspace=1); with the
// default search-only server they skip. Upstream search/page
// responses are fixture-mocked EXCEPT the save tokens, which
// must come from the real server (provenance design): the
// spec first obtains a real token through the API, then mocks
// the search response around it. Workspace API calls always
// hit the real server.
const { test, expect } = require('@playwright/test');

let workspaceEnabled = false;
let realToken = null;
let realFirstTitle = null;
let realPage = null;

test.beforeAll(async ({ request }) => {
  const home = await request.get('/');
  const html = await home.text();
  workspaceEnabled = html.includes('name="glm-workspace" content="1"');
  if (!workspaceEnabled) return;
  // one real upstream search to obtain a genuine save token
  const search = await request.get('/api/search?q=On%20the%20origin%20of%20species&libraries=internet-archive');
  if (search.ok()) {
    const data = await search.json();
    const first = (data.results || []).find(r => r.save_token);
    if (first) { realToken = first.save_token; realFirstTitle = first.title; }
  }
  const page = await request.get('/api/page?library=internet-archive&id=onoriginofspecie1859darw@20');
  if (page.ok()) {
    const data = await page.json();
    if (data.save_token) realPage = data;
  }
});

test.beforeEach(async ({ page }) => {
  test.skip(!workspaceEnabled, 'workspace not enabled on this server');
  await page.route('**/api/search**', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      query: '種の起源', search_kind: 'plain_bibliographic', options_applied: false,
      results: [{
        library_id: 'internet-archive', library_name: 'Internet Archive',
        record_id: 'onoriginofspecie1859darw', title: 'On the origin of species',
        author: 'Darwin, Charles', date: '1859', description: 'fixture',
        landing_url: 'https://archive.org/details/onoriginofspecie1859darw',
        rights: { statement: 'Public Domain' }, save_token: realToken || 'fixture-token',
      }],
      errors: [], retrieved_at: '2026-11-26T00:00:00Z',
    }),
  }));
});

test('workspace journey: project, save, note (XSS-safe), export, delete', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#workspace-section')).toBeVisible();

  // create a project
  await page.fill('#ws-new-project-title', 'ダーウィンの進化論');
  await page.click('#ws-create-project');
  await expect(page.locator('#ws-project-select')).toContainText('ダーウィンの進化論');

  // search (mocked) and save the document into the project
  await page.fill('#query', '種の起源');
  await page.click('#search-form button[type="submit"], #search-form button');
  const saveButton = page.locator('.ws-save-doc').first();
  await saveButton.waitFor({ state: 'visible' });
  test.skip(!realToken, 'no real save token available (upstream unreachable)');
  await saveButton.click();
  await expect(page.locator('#ws-status')).toContainText('保存しました');

  // The saved document is whatever the server-side snapshot
  // holds for the token (provenance by design - the fixture's
  // displayed title is NOT what gets saved).
  await page.click('[data-ws-tab="documents"]');
  await expect(page.locator('#ws-panel')).toContainText(realFirstTitle.slice(0, 24));

  // note with an XSS payload renders as text, never as markup
  await page.click('[data-ws-tab="notes"]');
  await page.fill('#ws-panel input[type="text"]', '<img src=x onerror=window.__xss=1>');
  await page.fill('#ws-panel textarea', '考察メモ <script>window.__xss=1</script>');
  await page.click('#ws-panel button:text("ノートを保存")');
  await expect(page.locator('#ws-panel')).toContainText('考察メモ');
  const xss = await page.evaluate(() => window.__xss === 1);
  expect(xss).toBe(false);
  await expect(page.locator('#ws-panel img')).toHaveCount(0);
  await expect(page.locator('#ws-panel script')).toHaveCount(0);

  // BibTeX download works
  await page.click('[data-ws-tab="export"]');
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.click('#ws-panel button:text("BibTeXをダウンロード")'),
  ]);
  expect(await download.suggestedFilename()).toContain('bib');

  // delete the project (two-step confirmation)
  page.on('dialog', dialog => dialog.accept());
  await page.click('#ws-panel button:text("プロジェクトを削除")');
  await expect(page.locator('#ws-project-select')).not.toContainText('ダーウィンの進化論');
});

test('citation journey: fetch a page, select text, save the citation', async ({ page }) => {
  test.skip(!realPage, 'no real page payload available (upstream unreachable)');
  await page.goto('/');
  await page.fill('#ws-new-project-title', '引用テスト');
  await page.click('#ws-create-project');
  await page.click('[data-ws-tab="cite"]');
  const inputs = page.locator('#ws-panel input[type="text"]');
  await inputs.nth(0).fill('internet-archive');
  await inputs.nth(1).fill('onoriginofspecie1859darw@20');
  await page.click('#ws-panel button:text("ページを取得")');
  const area = page.locator('#ws-panel textarea');
  await expect(area).not.toHaveValue('');
  await area.evaluate(node => { node.focus(); node.setSelectionRange(200, 320); });
  await page.click('#ws-panel button:text("選択範囲を引用として保存")');
  await expect(page.locator('#ws-status')).toContainText('引用を保存しました');
  await page.click('[data-ws-tab="citations"]');
  await expect(page.locator('#ws-panel')).toContainText('onoriginofspecie');
});

test('workspace layout on a mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.locator('#workspace-section')).toBeVisible();
  await expect(page.locator('#ws-project-select')).toBeVisible();
});
