// b11 final review section 32: MANDATORY research-tab journey.
//
// Runs against the same real workspace-enabled server as
// workspace.spec.js (real API, real SQLite, fixed upstream
// fixtures). The journey covers the research path end to end:
// project -> search -> save document -> save citation from the
// original page -> research question -> claim -> citation link
// -> evidence assessment -> graph -> report preview -> MD/JSON
// download -> reload re-display. HTTP-level semantics (status
// codes, validation, revalidation split) are covered separately
// by tests/test_b11_final_review.py - this file is the BROWSER
// journey and is reported separately.
const { test, expect } = require('@playwright/test');

test.setTimeout(120_000);

let workspaceEnabled = false;

test.beforeAll(async ({ request }) => {
  const home = await request.get('/');
  const html = await home.text();
  workspaceEnabled = html.includes('name="glm-workspace" content="1"');
});

test.beforeEach(async ({ page }) => {
  test.skip(!workspaceEnabled, 'workspace not enabled on this server');
});

test('research journey: question, claim, citation link, assessment, graph, report', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#workspace-section')).toBeVisible();

  await page.fill('#ws-new-project-title', '研究ジャーニー');
  await page.click('#ws-create-project');
  await expect(page.locator('#ws-project-select')).toContainText('研究ジャーニー');

  // search (IA fixture) and save the document + a citation
  const boxes = page.locator('input[name="library"]');
  for (let i = 0; i < await boxes.count(); i++) await boxes.nth(i).uncheck();
  await page.check('input[name="library"][value="internet-archive"]');
  await page.fill('#query', 'On the origin of species');
  await page.click('#search-form button[type="submit"], #search-form button');
  const saveButton = page.locator('.ws-save-doc').first();
  await saveButton.waitFor({ state: 'visible' });
  await saveButton.click();
  await expect(page.locator('#ws-status')).toContainText('保存しました');

  // original page -> citation, through the cite form (the IA
  // fixture identifier is onoriginofspecie1859darw, leaf 0)
  await page.click('[data-ws-tab="cite"]');
  await page.fill('#ws-panel input[placeholder="library_id"]', 'internet-archive');
  await page.fill('#ws-panel input[placeholder="page_id"]', 'onoriginofspecie1859darw@0');
  await page.click('#ws-panel button:text("ページを取得")');
  const area = page.locator('#ws-panel textarea');
  await expect(area).not.toHaveValue('');
  await area.evaluate((el) => { el.focus(); el.setSelectionRange(0, 24); });
  await page.click('#ws-panel button:text("選択範囲を引用として保存")');
  await expect(page.locator('#ws-status')).toContainText('引用を保存しました');

  // research tab: question and claim
  await page.click('[data-ws-tab="research"]');
  await page.fill('#ws-panel input[placeholder="研究質問を入力"]', '進化論はいつ発表されたか');
  await page.click('#ws-panel button:text("質問を構造化して保存")');
  await expect(page.locator('#ws-status')).toContainText('質問を保存しました');
  // the save re-renders the whole tab; wait for the LAST block
  // (claims section) so the claim input is the final DOM node,
  // not one a pending re-render is about to replace
  await expect(page.locator('#ws-panel')).toContainText('主張と根拠評価');
  await page.fill('#ws-panel input[placeholder="主張を入力"]', '1859年に種の起源が出版された。');
  await page.click('#ws-panel button:text("主張を構造化して保存")');
  await expect(page.locator('#ws-status')).toContainText('主張を保存しました');
  await expect(page.locator('#ws-panel')).toContainText('主張: 1859年に種の起源が出版された。');

  // link the saved citation to the claim, then assess it
  const ids = await page.evaluate(async () => {
    const pid = document.querySelector('#ws-project-select').value;
    const res = await fetch(`/api/workspace/citations?project_id=${encodeURIComponent(pid)}`);
    const data = await res.json();
    return { pid, citationId: (data.citations || [])[0]?.citation_id };
  });
  expect(ids.citationId).toBeTruthy();
  await page.fill('#ws-panel input[placeholder="引用ID"]', ids.citationId);
  await page.click('#ws-panel button:text("引用を関連付け")');
  await expect(page.locator('#ws-status')).toContainText('引用を関連付けました');
  await page.click('#ws-panel button:text("根拠を評価")');
  await expect(page.locator('#ws-status')).toContainText('根拠評価:');
  await expect(page.locator('#ws-panel')).toContainText('評価:');

  // graph is rendered
  await expect(page.locator('#ws-panel')).toContainText('根拠グラフ');

  // report preview + MD/JSON downloads
  await page.click('#ws-panel button:text("レポートを生成")');
  await expect(page.locator('#ws-status')).toContainText('レポート');
  await expect(page.locator('#ws-panel pre')).toContainText('Research Report');
  const mdLink = page.locator('#ws-panel a[download$=".md"]');
  await expect(mdLink).toBeVisible();
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    mdLink.click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.md$/);
  await expect(page.locator('#ws-panel a[download$=".json"]')).toBeVisible();

  // refresh button is honestly named (no original refetch)
  await expect(page.locator('#ws-panel button:text("状態を再構築（原典の再取得はしません）")')).toBeVisible();

  // reload: project, claim and artefacts re-display from the store
  await page.reload();
  await page.selectOption('#ws-project-select', ids.pid);
  await page.click('[data-ws-tab="research"]');
  await expect(page.locator('#ws-panel')).toContainText('主張: 1859年に種の起源が出版された。');
  await expect(page.locator('#ws-panel')).toContainText('研究成果物（信頼状態つき）');
  await expect(page.locator('#ws-panel')).toContainText('server_generated');
});
