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
      body: JSON.stringify({ available: false, status: 'llm_unavailable', reason: 'LLM is disabled', query: '発電', evidence: [], unverified: [], search: { results: [], errors: [] } }),
    });
  });

  await page.goto('/');
  await page.locator('#query').fill('発電');
  await page.getByRole('button', { name: 'AI回答' }).click();
  await expect(page.getByText(/AI回答は利用できません/)).toBeVisible();
});

const ANSWER_PAYLOAD = {
  status: 'answered',
  available: true,
  query: '発電水力の開発',
  answer: '検証済みの根拠ページのOCR本文に基づく回答です。',
  citations: [{
    citation_key: 'ndl:994120:994120_50',
    library_id: 'ndl',
    library_name: 'National Diet Library',
    record_id: '994120',
    page_id: '994120_50',
    digital_frame: 50,
    title: '發電水力の開發',
    image_url: 'https://dl.ndl.go.jp/api/iiif/994120/R0000050/full/full/0/default.jpg',
    landing_url: 'https://dl.ndl.go.jp/pid/994120',
  }],
  evidence: [{
    citation_key: 'ndl:994120:994120_50',
    library_id: 'ndl',
    library_name: 'National Diet Library',
    record_id: '994120',
    page_id: '994120_50',
    digital_frame: 50,
    title: '發電水力の開發',
    ocr_text: '發電水力の開發は明治四十三年に始まり、臨時發電水力調査局が設置された。',
    ocr_quality: { score: 1.0 },
    matched_term: '発電水力',
    image_url: 'https://dl.ndl.go.jp/api/iiif/994120/R0000050/full/full/0/default.jpg',
    landing_url: 'https://dl.ndl.go.jp/pid/994120',
    rights: { statement: '資料単位で確認' },
    relevance: { status: 'relevant', score: 0.85, matched_concepts: ['水力発電'], missing_concepts: [], reasons: ['中心概念を確認: 水力発電', '時代名「明治」が本文に現れる'] },
    semantics: { relation: 'supports', checker: 'rules-v1', demand: 'occurrence', reasons: ['実現・開始を示す記述が中心概念と結びついている'], stance_sentences: {} },
  }],
  related: [{
    citation_key: 'ndl:111:111_10',
    library_id: 'ndl',
    library_name: 'National Diet Library',
    record_id: '111',
    page_id: '111_10',
    title: '電信沿革史',
    image_url: null,
    landing_url: 'https://dl.ndl.go.jp/pid/111',
    relevance: { status: 'partially_relevant', score: 0.35, matched_concepts: [], missing_concepts: ['水力発電'], reasons: ['中心概念が本文にない: 水力発電'] },
  }],
  unverified: [{ library_id: 'ndl', record_id: '123456', page_id: '123456_7', reason: 'OCR text is very short' }],
  claims: [{
    text: '發電水力の開發は明治四十三年に始まり、臨時發電水力調査局が設置された',
    citations: ['ndl:994120:994120_50'],
    support: 'supported',
    support_detail: 'lexical overlap 1.00 over 1 cited page(s)',
    overlap: 1.0,
  }],
  limitations: ['Mock provider'],
  search: { results: [], errors: [] },
};

test('answer view links citations to evidence and runs IIIF verification', async ({ page }) => {
  await page.route('**/api/answer**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ANSWER_PAYLOAD) });
  });
  await page.route('**/api/verify**', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'verified',
        checks: {
          page_identity: { ok: true, detail: 'match' },
          image_reachable: { ok: true, detail: 'HTTP 206' },
        },
      }),
    });
  });

  await page.goto('/');
  await page.locator('#query').fill('発電水力の開発');
  await page.getByRole('button', { name: 'AI回答' }).click();

  await expect(page.getByText('検証済みの根拠ページのOCR本文に基づく回答です。')).toBeVisible();
  await expect(page.getByText('検証済みOCR')).toBeVisible();
  await expect(page.getByText(/OCR text is very short/)).toBeVisible();

  await expect(page.getByText('裏付けあり')).toBeVisible();
  await expect(page.locator('.evidence-thumb')).toHaveCount(1);
  await expect(page.getByText('関連性あり', { exact: true })).toBeVisible();
  await expect(page.getByText('前提を支持', { exact: true })).toBeVisible();
  await expect(page.getByText(/参考資料（回答の根拠には未採用）/)).toBeVisible();
  await expect(page.getByText('電信沿革史')).toBeVisible();
  await expect(page.getByText('一部関連', { exact: true })).toBeVisible();

  const chip = page.locator('.chip').first();
  await chip.click();
  await expect(page.locator('.evidence-card')).toBeInViewport();

  await page.getByRole('button', { name: 'IIIFで原本を検証' }).click();
  await expect(page.getByText('原本検証: verified')).toBeVisible();
  await expect(page.getByText(/image_reachable/)).toBeVisible();
});

test('insufficient evidence is reported plainly', async ({ page }) => {
  await page.route('**/api/answer**', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'insufficient_evidence', available: false, query: '明治時代のスマートフォンの普及について教えて', answer: null, citations: [], evidence: [], unverified: [],
        reason: '質問の中心概念（スマートフォン）を裏付けるOCR本文が確認できませんでした。関連する資料は見つかりましたが、質問への関連性が不足するため、回答の根拠には採用していません（参考資料として表示します）。',
        related_documents: [{
          citation_key: 'ndl:111:111_10', library_id: 'ndl', record_id: '111', page_id: '111_10', title: '電信沿革史',
          image_url: null, landing_url: 'https://dl.ndl.go.jp/pid/111',
          relevance_status: 'irrelevant', relevance_reasons: ['中心概念が本文にない: スマートフォン', '一致したのは周辺語のみ: 通信'],
        }],
        search: { results: [], errors: [] },
      }),
    });
  });

  await page.goto('/');
  await page.locator('#query').fill('明治時代のスマートフォンの普及について教えて');
  await page.getByRole('button', { name: 'AI回答' }).click();
  await expect(page.getByText(/中心概念（スマートフォン）を裏付けるOCR本文が確認できませんでした/)).toBeVisible();
  await expect(page.getByText(/参考資料（回答の根拠には未採用）/)).toBeVisible();
  await expect(page.getByText('関連性なし', { exact: true })).toBeVisible();
  await expect(page.getByText(/周辺語のみ: 通信/)).toBeVisible();
});

test('corrected premise is shown with its quoted basis', async ({ page }) => {
  await page.route('**/api/answer**', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'corrected_premise', available: true, query: '明治時代の地下鉄の建設について教えて',
        answer: '質問の前提（地下鉄が明治時代に存在・実現していた）は、確認できた資料では支持されません。『東京地下鉄道史』には「地下鉄は昭和二年に開業した」とあり、前提とは異なる時期・状況が示されています。',
        citations: [{ citation_key: 'ndl:222:222_10', library_id: 'ndl', library_name: 'NDL', record_id: '222', page_id: '222_10', digital_frame: 10, title: '東京地下鉄道史', image_url: null, landing_url: 'https://dl.ndl.go.jp/pid/222' }],
        correction: { basis_citation_key: 'ndl:222:222_10', quotes: ['地下鉄は昭和二年に開業した'], reasons: ['中心概念の開始・開業が対象時代より後の年代と明記されている'] },
        claims: [], evidence: [], unverified: [], limitations: [],
        search: { results: [], errors: [] },
      }),
    });
  });

  await page.goto('/');
  await page.locator('#query').fill('明治時代の地下鉄の建設について教えて');
  await page.getByRole('button', { name: 'AI回答' }).click();
  await expect(page.getByText('前提の訂正', { exact: true })).toBeVisible();
  await expect(page.getByText(/訂正の根拠（原文からの引用）/)).toBeVisible();
  await expect(page.getByText('地下鉄は昭和二年に開業した', { exact: true })).toBeVisible();
});

test('language toggle switches the UI to English', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Switch language' }).click();
  await expect(page.getByRole('button', { name: 'Search' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'AI answer' })).toBeVisible();
});


const COMPARE_PAYLOAD = {
  status: 'compared',
  aspects: ['送電'],
  documents: [
    { library_id: 'ndl', record_id: '994120', title: '發電水力の開發', date: 1911, landing_url: 'https://dl.ndl.go.jp/pid/994120', error: null, verified_pages: 2 },
    { library_id: 'ndl', record_id: '1018770', title: '水力電気 上巻', date: 1925, landing_url: 'https://dl.ndl.go.jp/pid/1018770', error: null, verified_pages: 2 },
  ],
  rows: [{
    aspect: '送電',
    documents: {
      '994120': { found: true, excerpts: [{ aspect: '送電', page_id: '994120_40', citation_key: 'ndl:994120:994120_40', image_url: 'https://dl.ndl.go.jp/api/iiif/994120/R0000040/full/full/0/default.jpg', excerpt: '發電した電力を近傍へ送電した' }] },
      '1018770': { found: true, excerpts: [{ aspect: '送電', page_id: '1018770_14', citation_key: 'ndl:1018770:1018770_14', image_url: 'https://dl.ndl.go.jp/api/iiif/1018770/R0000014/full/full/0/default.jpg', excerpt: '高壓送電が主流となった' }] },
    },
    shared_terms: ['送電', '水力'],
    unique_terms: { '994120': ['水車'], '1018770': ['資本'] },
  }],
  notes: ['比較は検証済みOCRページのテキストに基づく機械的な対照です。'],
};

test('compare view renders aspect rows from the compare API', async ({ page }) => {
  await page.route('**/api/compare**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(COMPARE_PAYLOAD) });
  });
  await page.goto('/');
  await page.getByRole('button', { name: '比較する' }).click();
  await expect(page.getByText('高壓送電が主流となった')).toBeVisible();
  await expect(page.getByText('發電した電力を近傍へ送電した')).toBeVisible();
  await expect(page.getByText(/共通する語/)).toBeVisible();
  await expect(page.getByText(/機械的な対照/)).toBeVisible();
});
