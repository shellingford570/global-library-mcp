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
  await expect(page.getByRole('button', { name: 'Search', exact: true })).toBeVisible();
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

test('research materials mode shows candidates with states and reasons', async ({ page }) => {
  await page.route('**/api/materials**', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        mode: 'research_materials',
        note: '関連候補は質問への答えを証明する資料ではありません。抜粋と原本を確認し、ご自身で判断してください。',
        query: '明治の電信',
        materials: [{
          citation_key: 'ndl:1:1_5', library_id: 'ndl', record_id: '1', page_id: '1_5',
          title: '電信史', author: 'テスト著者', date: '1910', image_url: null,
          rights: {}, admitted_as_evidence: false,
          states: { discovered: true, accessible: true, source_verified: true,
                    relevant_candidate: true, supporting_passage: false,
                    assessed_evidence: false, rejected_for_answer: true },
          excerpts: [{ text: '電信は明治二年に開局した。' }],
          not_admitted_reasons: ['出来事と時代を直接結び付ける記述（時代アンカー）が確認できない'],
        }],
      }),
    });
  });
  await page.goto('/');
  await page.locator('#query').fill('明治の電信');
  await page.locator('#materials-button').click();
  await expect(page.getByText('電信史')).toBeVisible();
  await expect(page.getByText('電信は明治二年に開局した。')).toBeVisible();
  await expect(page.getByText(/回答に採用しない理由/)).toBeVisible();
  await expect(page.getByText(/証明する資料ではありません/)).toBeVisible();
  // Phase 9-G: citation copy button is present, and the
  // admitted-only filter hides this non-admitted candidate.
  await expect(page.locator('.copy-citation')).toHaveCount(1);
  await page.locator('#materials-admitted-only').check();
  await expect(page.getByText('電信史')).toHaveCount(0);
});

test('scope and terms section explains the beta posture', async ({ page }) => {
  await page.goto('/');
  const scope = page.locator('.scope-panel');
  await expect(scope).toBeVisible();
  await expect(scope).toContainText('対応範囲と利用条件');
  await expect(scope).toContainText('AI回答は実験機能です');
  await expect(scope).toContainText('存在しないことを意味しません');
});

test('b3.1 staged flow: bibliographic results stay visible during and after materials', async ({ page }) => {
  await page.route('**/api/search**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      query: '発電', results: [{ library_id: 'ndl', library_name: 'NDL', record_id: '1', title: '書誌タイトル', author: '著者', date: '1900', landing_url: 'https://example.org/1', rights: {} }], errors: [],
    }) });
  });
  let releaseMaterials;
  const gate = new Promise((resolve) => { releaseMaterials = resolve; });
  await page.route('**/api/materials**', async route => {
    await gate;
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      mode: 'standard', note: 'note', query: '発電',
      timings: { total_s: 3.2 }, http_stats: { requests: 12 },
      materials: [{ citation_key: 'ndl:1:1_1', library_id: 'ndl', record_id: '1', page_id: '1_1', title: '資料タイトル', author: '著者', date: '1900', image_url: null, landing_url: 'https://example.org/1',
        rights: { status: 'Public Domain' }, admitted_as_evidence: true,
        access_state: { bibliographic: true, ocr_fetched: true, mapping_confirmed: true, passage_found: true, assessed_as_evidence: true },
        states: { discovered: true, accessible: true, source_verified: true, relevant_candidate: true, supporting_passage: true, assessed_evidence: true, rejected_for_answer: false },
        excerpts: [{ text: '発電の抜粋。' }], not_admitted_reasons: [] }],
    }) });
  });
  await page.goto('/');
  await page.locator('#query').fill('発電');
  await page.locator('#search-form button[type="submit"]').click();
  await expect(page.getByText('書誌タイトル')).toBeVisible();
  await page.locator('#materials-button').click();
  // While the investigation runs, the bibliographic result stays on screen.
  await expect(page.getByText('書誌タイトル')).toBeVisible();
  releaseMaterials();
  await expect(page.locator('#materials-results').getByText('資料タイトル')).toBeVisible();
  // After it completes, both remain visible, with access states, rights and perf.
  await expect(page.getByText('書誌タイトル')).toBeVisible();
  await expect(page.locator('#materials-results').getByText(/OCR取得/)).toBeVisible();
  await expect(page.locator('#materials-results').getByText(/Public Domain/)).toBeVisible();
  await expect(page.locator('#stage-status')).toContainText('実HTTPリクエスト 12 件');
});

test('b3.1 cancel: server-confirmed cancellation is shown', async ({ page }) => {
  await page.route('**/api/cancel**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ op_id: 'x', state: 'cancelled' }) });
  });
  await page.route('**/api/materials**', async route => {
    await new Promise((resolve) => setTimeout(resolve, 30000));
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
  await page.goto('/');
  await page.locator('#query').fill('発電');
  await page.locator('#materials-button').click();
  await expect(page.locator('#cancel-button')).toBeVisible();
  await page.locator('#cancel-button').click();
  await expect(page.locator('#stage-status')).toContainText('キャンセルしました');
});

test('b3.1 partial failure: status and reasons are visible', async ({ page }) => {
  await page.route('**/api/materials**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      mode: 'standard', note: 'note', query: '発電',
      errors: [{ library_id: 'loc', error: 'search deadline exceeded (10s); partial result' }],
      timings: { total_s: 9.9 }, http_stats: { requests: 20 },
      materials: [{ citation_key: null, library_id: 'ndl', record_id: '2', page_id: null, title: '部分資料', author: '', date: '', image_url: null, landing_url: 'https://example.org/2',
        rights: {}, admitted_as_evidence: false,
        access_state: { bibliographic: true, ocr_fetched: false, mapping_confirmed: false, passage_found: false, assessed_as_evidence: false },
        states: { discovered: true, accessible: false, source_verified: false, relevant_candidate: false, supporting_passage: false, assessed_evidence: false, rejected_for_answer: true },
        excerpts: [], not_admitted_reasons: ['ページを取得しなかった'] }],
    }) });
  });
  await page.goto('/');
  await page.locator('#query').fill('発電');
  await page.locator('#materials-button').click();
  await expect(page.locator('#stage-status')).toContainText('部分的に完了しました');
  await expect(page.locator('#materials-results').getByText('部分資料')).toBeVisible();
  await expect(page.locator('#materials-results').getByText(/OCR取得/)).toBeVisible();
});

// ---- b5 final review (S18): library directory + ID lookup ----

const LIBS_FIXTURE = [
  { id: 'bsb', name: 'BSB Fixture', region: 'Europe', country: 'DE', languages: ['de'], implementation_status: 'implemented', official_site: 'https://example.org/bsb', verification: 'fixture', capability_status: { catalog_search: 'unsupported', page_ocr: 'live_page_verified' } },
  { id: 'ndl', name: 'NDL Fixture', region: 'Asia', country: 'JP', languages: ['ja'], implementation_status: 'implemented', official_site: 'https://example.org/ndl', verification: 'fixture', capability_status: { catalog_search: 'live_catalog_verified', page_ocr: 'live_page_verified' } },
  { id: 'fr-research', name: 'FR Research Fixture', region: 'Europe', country: 'FR', languages: ['fr'], implementation_status: 'research_only', official_site: 'https://example.org/fr', verification: 'fixture', capability_status: { catalog_search: 'research_only', page_ocr: 'implemented' } },
];

async function mockLibraries(page) {
  await page.route('**/api/libraries**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ libraries: LIBS_FIXTURE }) });
  });
}

test('library directory filters by region, language and OCR capability', async ({ page }) => {
  await mockLibraries(page);
  await page.goto('/');
  await expect(page.getByText('BSB Fixture')).toBeVisible();
  await expect(page.getByText('NDL Fixture')).toBeVisible();
  await expect(page.getByText('FR Research Fixture')).toBeVisible();
  // BSB must not be presented as keyword-searchable.
  await expect(page.getByText('catalog_search: unsupported')).toBeVisible();
  await page.locator('#lib-region').selectOption('Europe');
  await expect(page.getByText('NDL Fixture')).toHaveCount(0);
  await expect(page.getByText('BSB Fixture')).toBeVisible();
  await page.locator('#lib-region').selectOption('');
  await page.locator('#lib-ocr-only').check();
  await expect(page.getByText('FR Research Fixture')).toHaveCount(0);
  await expect(page.getByText('NDL Fixture')).toBeVisible();
  await page.locator('#lib-ocr-only').uncheck();
  await page.locator('#lib-lang').selectOption('de');
  await expect(page.getByText('BSB Fixture')).toBeVisible();
  await expect(page.getByText('NDL Fixture')).toHaveCount(0);
});

test('ID lookup opens a BSB document with its rights classification', async ({ page }) => {
  await mockLibraries(page);
  await page.route('**/api/document**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      library_id: 'bsb', record_id: 'bsb00000001', title: 'Fixture Book', author: 'Author, A.', date: '1854',
      page_count: 3, landing_url: 'https://example.org/bsb00000001',
      rights: { statement: 'NoC-NC/1.0', classification: 'rightsstatements-noc-nc-noncommercial' },
    }) });
  });
  await page.goto('/');
  await page.locator('#lookup-library').selectOption('bsb');
  await page.locator('#lookup-record').fill('bsb00000001');
  await page.locator('#lookup-document-button').click();
  await expect(page.locator('#lookup-results').getByText('Fixture Book')).toBeVisible();
  await expect(page.locator('#lookup-results').getByText(/rightsstatements-noc-nc-noncommercial/)).toBeVisible();
});

test('ID lookup shows page mapping state and in-document coverage', async ({ page }) => {
  await mockLibraries(page);
  await page.route('**/api/page**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      library_id: 'bsb', page_id: 'bsb00000001@2', verified_mapping: true,
      contents: 'Wasserwerk page text', image_url: 'https://example.org/img.jpg', landing_url: 'https://example.org/bsb00000001',
    }) });
  });
  await page.route('**/api/in-document**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      matches: { list: [{ page_id: 'bsb00000001@2', snippet: '...Wasserwerk...', mapping_status: 'verified' }] },
      pages_searched: 20, total_pages: 172, complete: false, partial_failures: [],
    }) });
  });
  await page.goto('/');
  await page.locator('#lookup-library').selectOption('bsb');
  await page.locator('#lookup-record').fill('bsb00000001');
  await page.locator('#lookup-page').fill('bsb00000001@2');
  await page.locator('#lookup-page-button').click();
  await expect(page.locator('#lookup-results').getByText('原本対応：検証済み')).toBeVisible();
  await expect(page.locator('#lookup-results').getByText(/Wasserwerk page text/)).toBeVisible();
  await page.locator('#lookup-query').fill('Wasserwerk');
  await page.locator('#lookup-search-button').click();
  await expect(page.locator('#lookup-results').getByText(/20\/172 pages \(partial\)/)).toBeVisible();
  await expect(page.locator('#lookup-results').getByText('...Wasserwerk...')).toBeVisible();
});
