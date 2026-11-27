const form = document.querySelector('#search-form');
const query = document.querySelector('#query');
const results = document.querySelector('#results');
const title = document.querySelector('#result-title');
const meta = document.querySelector('#result-meta');
const notice = document.querySelector('#notice');
const answerButton = document.querySelector('#answer-button');
const materialsButton = document.querySelector('#materials-button');
const searchButton = form.querySelector('button[type="submit"]');
const langToggle = document.querySelector('#lang-toggle');

const I18N = {
  ja: {
    status: 'OCR根拠つき回答 / 検証済み原本',
    h1: '世界の原資料へ、<em>検証可能な経路</em>で。',
    lede: '図書館とデジタルアーカイブを横断検索し、ページ単位のOCRと原本画像を確認できる研究資料検索サービスです。AI回答は実験機能として分離され、未確認の情報は隠さず表示します。',
    scopeTitle: '対応範囲と利用条件',
    librariesTitle: '対応図書館一覧',
    lookupTitle: 'ID指定で資料を開く',
    lookupRecord: '資料ID',
    lookupPage: 'ページID',
    lookupQuery: '文書内検索の語',
    lookupDocumentButton: '資料情報を開く',
    lookupPageButton: 'ページOCRを開く',
    lookupSearchButton: '文書内を検索',
    lookupHint: 'ID指定型の機関（BSB・e-rara・LoC新聞）はキーワード検索ではなく、既知の資料IDから開きます。',
    mappingVerified: '原本対応：検証済み',
    mappingUnverified: '原本対応：未検証',
    coverageLabel: '検索範囲',
    rightsClassLabel: '権利区分',
    regionAll: '地域：すべて',
    langAll: '言語：すべて',
    ocrOnly: 'ページOCR対応のみ',
    implementedLabel: '実装済み',
    officialSiteLabel: '公式サイト',
    researchOnlyLabel: '調査段階',
    scopeLibrariesTitle: '対応機関',
    scopeLibraries: '国立国会図書館（NDL）、Internet Archive、Library of Congress は検索・OCR・原本画像に対応。Gallica は当ネットワークから取得できない場合があります。DDB・Europeana は書誌検索中心です。それ以外の機関は調査中であり、対応を保証しません。',
    scopeTermsTitle: '利用条件',
    scopeTerms: '権利表示は資料ごとに各機関の表示をそのまま示します。権利が不明な資料を再配布可能とは表示しません。抜粋は短い引用と原本へのリンクを基本とし、貸出限定などアクセス制限のある資料は取得しません。',
    scopeAiTitle: 'AI機能について',
    scopeAi: 'AI回答は実験機能です。Research Beta の初期設定では無効で、本サービスは研究資料の検索・OCR・原本確認のために提供されます。検索結果は「回答の証明」ではなく、利用者が調査するための研究資料です。',
    scopeNoResultTitle: '見つからなかった場合',
    scopeNoResult: '検索予算（初期設定 Standard 25 リクエスト）の範囲で根拠が見つからなかったことは、その事実が歴史上存在しないことを意味しません。対象機関・取得範囲・図書館側の制限により結果は変わります。',
    budgetNote: '検索予算と対象範囲の中で根拠が見つかりませんでした。これは、その事実が存在しないことを意味しません。',
    queryLabel: '調べたいこと',
    queryPlaceholder: '例：明治時代の日本の発電技術',
    searchButton: '検索する',
    answerButton: 'AI回答',
    materialsButton: '研究資料',
    modeQuick: '簡易（書誌のみ）',
    modeStandard: '標準',
    modeDeep: '詳細',
    cancelButton: 'キャンセル',
    stageSearchDone: '書誌検索が完了しました。「研究資料」ボタンで選択中のモードの詳細調査（OCR・原本確認）を行えます。',
    statusRunning: '詳細調査中…',
    statusComplete: '詳細調査が完了しました。',
    statusPartial: '部分的に完了しました（一部の機関で失敗または制限に達しました）。',
    statusFailed: '詳細調査に失敗しました。',
    statusCancelled: 'キャンセルしました。',
    perfSummary: (s, n) => `処理時間 ${s} 秒 / 実HTTPリクエスト ${n} 件`,
    statusTimeout: '調査が時間上限に達したため停止しました（部分結果）。',
    statusCancelRequested: 'キャンセルを要求しました（サーバー側の停止確認待ち）。',
    accessBiblio: '書誌',
    accessOcr: 'OCR取得',
    accessMapping: 'ページ対応',
    accessPassage: '原文箇所',
    accessAssessed: '根拠評価',
    materialsTitle: '研究資料（関連候補）',
    copyCitation: '引用をコピー', copied: 'コピーしました', admittedOnly: '根拠として採用された資料のみ', sourcePage: '資料ページ',
    authorPlaceholder: '著者名（例：カント）', titlePlaceholder: '原題・翻訳題（例：純粋理性批判）',
    expandMulti: '多言語展開', expandHist: '歴史的表記展開',
    discoveryTitle: '検索の展開（資料発見のみ・根拠判定には使いません）',
    featuresLine: (f) => `検索方式: 語彙・厳密信号${f.research_ranker ? ' + ResearchRanker（理由表示あり）' : ''} / 意味検索: ${f.semantic_search ? `利用可能（${f.semantic_model}・ローカル）` : '未導入（語彙検索のみ）'}`,
    rankingReasonsLabel: 'ランキング理由',
    queryLanguageLabel: '質問の言語', matchedVariantLabel: '発見した検索語', discoveryReasonsLabel: '表示理由',
    workLinkLabel: '作品候補', ambiguousAuthorLabel: '同名の著者が複数いるため特定していません', variantExecuted: '実行済み', variantNotExecuted: '未実行',
    bsbHandoffLabel: 'BSB/MDZで原本を確認', dupGroupLabel: '同一作品の候補グループ',
    materialsNote: '関連候補は質問への答えを証明する資料ではありません。抜粋と原本を確認し、ご自身で判断してください。',
    stateDiscovered: '資料発見', stateAccessible: 'ページ取得', stateVerified: '原本対応確認',
    stateCandidate: '関連候補', stateAssessed: '根拠として採用', stateRejected: '回答には不採用',
    notAdmittedLabel: '回答に採用しない理由',
    excerptsLabel: '関連するOCR抜粋',
    demoBadge: 'デモ／テストモード（MockProvider）— 実際のAI回答ではありません',
    partialTag: '部分回答（検証済みの主張のみ）',
    resultsTitle: '検索結果',
    notice: '検索結果は資料の発見を支援するものです。引用前に原本ページと権利表示を確認してください。',
    emptyHint: '質問を入力すると、対応機関の記録がここに表示されます。',
    footerNote: '未確認事項は unknown',
    recordsFor: q => `「${q}」の記録`,
    countSuffix: '件',
    retrievedUnknown: '取得時刻 unknown',
    noDescription: '資料の詳細説明は提供されていません。',
    rightsLabel: '権利',
    publishedUnknown: '出版年 unknown',
    backToSource: '原本へ戻る ↗',
    searching: '各機関へ問い合わせています…',
    searchingNotice: 'ライブAPIの応答を統合しています。機関ごとの失敗は部分結果とともに表示されます。',
    noMatches: '一致する記録は見つかりませんでした。検索語を変えて試してください。',
    answering: '根拠を集めています…',
    requestFailed: 'リクエストに失敗しました',
    answerTag: '根拠つき回答',
    citationsLabel: '引用（クリックで根拠ページへ）',
    limitationsLabel: '制限',
    verifiedBadge: '検証済みOCR',
    unverifiedTitle: '未確認（根拠として使えないもの）',
    frameLabel: 'コマ',
    qualityLabel: 'OCR品質',
    matchedTermLabel: '一致語',
    viewImage: '原本画像を見る ↗',
    viewRecord: '資料ページ ↗',
    verifyButton: 'IIIFで原本を検証',
    verifying: '検証中…',
    verifyVerified: '原本検証: verified',
    verifyFailed: '原本検証: failed',
    verifyUnsupported: '原本検証: unsupported',
    statusInsufficient: '確認できる根拠（検証済みのOCRページ）が見つかりませんでした。',
    statusUnavailable: 'AI回答は利用できません',
    statusWithheld: '引用の検証に失敗したため、回答を表示しません。',
    evidenceTitle: '根拠ページ',
    claimsTitle: '主張ごとの根拠チェック（機械的スクリーニング）',
    supportSupported: '裏付けあり',
    supportUncertain: '要確認',
    supportUnsupported: '根拠なし',
    supportConflicting: '資料間で矛盾',
    supportNotChecked: '未検証',
    relevanceLabel: '質問への関連性（機械的スクリーニング）',
    relRelevant: '関連性あり',
    relPartial: '一部関連',
    relIrrelevant: '関連性なし',
    relUncertain: '判定不能',
    relNotChecked: '未検証',
    relatedTitle: '参考資料（回答の根拠には未採用）',
    semLabel: '意味判定（自動スクリーニング）',
    semSupports: '前提を支持', semContradicts: '前提と矛盾', semMentionsOnly: '言及のみ',
    semInsufficient: '情報なし', semUncertain: '判定不能', semNotChecked: '未検証',
    correctedTag: '前提の訂正',
    correctionBasis: '訂正の根拠（原文からの引用）',
    statusAnswerWithheld: '回答を保留しました',
    compareTitle: '文献比較',
    compareDocA: '文献A（機関:資料ID）',
    compareDocB: '文献B（機関:資料ID）',
    compareAspects: '比較観点（カンマ区切り）',
    compareButton: '比較する',
    comparing: '比較しています…',
    compareNotFound: 'この観点の検証済みページは見つかりませんでした',
    sharedTerms: '共通する語',
    uniqueTerms: 'この資料だけの語',
    langHintJa: '日本語の質問として処理します',
    langHintEn: '英語の質問として処理します（資料は各言語で検索されます）',
  },
  en: {
    status: 'OCR-grounded answers / verified originals',
    h1: 'Primary sources worldwide, by a <em>verifiable path</em>.',
    lede: 'A research-materials search service across libraries and digital archives, with page-level OCR and original images you can verify. AI answers are a separate experimental feature, and unverified information is shown, not hidden.',
    scopeTitle: 'Scope and terms',
    librariesTitle: 'Library directory',
    lookupTitle: 'Open a document by ID',
    lookupRecord: 'Record ID',
    lookupPage: 'Page ID',
    lookupQuery: 'In-document search term',
    lookupDocumentButton: 'Open document',
    lookupPageButton: 'Open page OCR',
    lookupSearchButton: 'Search in document',
    lookupHint: 'ID-addressed libraries (BSB, e-rara, LoC newspapers) open from a known record ID, not by keyword search.',
    mappingVerified: 'Page mapping: verified',
    mappingUnverified: 'Page mapping: unverified',
    coverageLabel: 'Coverage',
    rightsClassLabel: 'Rights class',
    regionAll: 'Region: all',
    langAll: 'Language: all',
    ocrOnly: 'Page-OCR capable only',
    implementedLabel: 'Implemented',
    officialSiteLabel: 'Official site',
    researchOnlyLabel: 'Research only',
    scopeLibrariesTitle: 'Libraries',
    scopeLibraries: 'The National Diet Library (NDL), Internet Archive and Library of Congress support search, OCR and original images. Gallica may be unreachable from some networks. DDB and Europeana are bibliographic-search centred. All other institutions are under research and are not promised.',
    scopeTermsTitle: 'Terms of use',
    scopeTerms: 'Rights statements are shown verbatim from each library, per item. Material with unknown rights is never presented as redistributable. Excerpts are short quotations with links to the original, and access-restricted (e.g. lending-only) items are not fetched.',
    scopeAiTitle: 'About the AI features',
    scopeAi: 'AI answers are experimental. They are disabled by default in the Research Beta; this service is provided for searching research materials, reading OCR and checking originals. Search results are materials for your own investigation, not proof of an answer.',
    scopeNoResultTitle: 'When nothing is found',
    scopeNoResult: 'Finding no evidence within the search budget (Standard 25 requests by default) does not mean the fact does not exist historically. Results depend on the libraries covered, the retrieval scope and each library\'s own limits.',
    budgetNote: 'No evidence was found within the search budget and scope. That does not mean the fact does not exist.',
    queryLabel: 'What do you want to research?',
    queryPlaceholder: 'e.g. hydroelectric power in Meiji-era Japan',
    searchButton: 'Search',
    answerButton: 'AI answer',
    materialsButton: 'Research materials',
    modeQuick: 'Quick (bibliographic only)',
    modeStandard: 'Standard',
    modeDeep: 'Deep',
    cancelButton: 'Cancel',
    stageSearchDone: 'Bibliographic search complete. Use "Research materials" to run the detailed investigation (OCR and original checks) in the selected mode.',
    statusRunning: 'Investigating…',
    statusComplete: 'Investigation complete.',
    statusPartial: 'Partially complete (some libraries failed or hit a limit).',
    statusFailed: 'Investigation failed.',
    statusCancelled: 'Cancelled.',
    perfSummary: (s, n) => `Elapsed ${s}s / ${n} actual HTTP requests`,
    statusTimeout: 'Investigation stopped at the time limit (partial results).',
    statusCancelRequested: 'Cancellation requested (waiting for server confirmation).',
    accessBiblio: 'Bibliographic',
    accessOcr: 'OCR fetched',
    accessMapping: 'Page mapping',
    accessPassage: 'Passage found',
    accessAssessed: 'Assessed as evidence',
    materialsTitle: 'Research materials (candidates)',
    copyCitation: 'Copy citation', copied: 'Copied', admittedOnly: 'Admitted as evidence only', sourcePage: 'Record page',
    authorPlaceholder: 'Author (e.g. Kant)', titlePlaceholder: 'Original / translated title',
    expandMulti: 'Multilingual expansion', expandHist: 'Historical spellings',
    discoveryTitle: 'Search expansion (discovery only; never used for evidence admission)',
    featuresLine: (f) => `Search: lexical + strict signals${f.research_ranker ? ' + ResearchRanker (with reasons)' : ''} / Semantic search: ${f.semantic_search ? `available (${f.semantic_model}, local)` : 'not installed (lexical only)'}`,
    rankingReasonsLabel: 'Ranking reasons',
    queryLanguageLabel: 'Query language', matchedVariantLabel: 'Found by search term', discoveryReasonsLabel: 'Why shown',
    workLinkLabel: 'Work candidate', ambiguousAuthorLabel: 'Several authors share this name; not identified', variantExecuted: 'executed', variantNotExecuted: 'not executed',
    bsbHandoffLabel: 'Check the original at BSB/MDZ', dupGroupLabel: 'Same-work candidate group',
    materialsNote: 'Candidates do not prove an answer. Read the excerpts and originals and judge for yourself.',
    stateDiscovered: 'Discovered', stateAccessible: 'Page fetched', stateVerified: 'Source verified',
    stateCandidate: 'Relevant candidate', stateAssessed: 'Admitted as evidence', stateRejected: 'Not admitted for answers',
    notAdmittedLabel: 'Why not admitted',
    excerptsLabel: 'Relevant OCR excerpts',
    demoBadge: 'Demo / test mode (MockProvider) - not a real AI answer',
    partialTag: 'Partial answer (verified claims only)',
    resultsTitle: 'Results',
    notice: 'Search results help you discover sources. Check the original page and its rights statement before citing.',
    emptyHint: 'Ask a question and records from the connected institutions will appear here.',
    footerNote: 'Unverified items are shown as unknown',
    recordsFor: q => `Records for "${q}"`,
    countSuffix: ' records',
    retrievedUnknown: 'retrieved at unknown',
    noDescription: 'No description is provided for this record.',
    rightsLabel: 'Rights',
    publishedUnknown: 'year unknown',
    backToSource: 'Back to the original ↗',
    searching: 'Querying each institution…',
    searchingNotice: 'Combining live API responses. Per-institution failures are shown with partial results.',
    noMatches: 'No matching records were found. Try different terms.',
    answering: 'Collecting evidence…',
    requestFailed: 'The request failed',
    answerTag: 'EVIDENCE-GROUNDED ANSWER',
    citationsLabel: 'Citations (click to jump to the evidence page)',
    limitationsLabel: 'Limitations',
    verifiedBadge: 'Verified OCR',
    unverifiedTitle: 'Unverified (not usable as evidence)',
    frameLabel: 'frame',
    qualityLabel: 'OCR quality',
    matchedTermLabel: 'matched term',
    viewImage: 'View original image ↗',
    viewRecord: 'Record page ↗',
    verifyButton: 'Verify original via IIIF',
    verifying: 'Verifying…',
    verifyVerified: 'Original verification: verified',
    verifyFailed: 'Original verification: failed',
    verifyUnsupported: 'Original verification: unsupported',
    statusInsufficient: 'No verifiable evidence (verified OCR pages) could be found.',
    statusUnavailable: 'The AI answer is unavailable',
    statusWithheld: 'The answer is withheld because citation validation failed.',
    evidenceTitle: 'Evidence pages',
    claimsTitle: 'Claim-by-claim grounding check (mechanical screening)',
    supportSupported: 'supported',
    supportUncertain: 'uncertain',
    supportUnsupported: 'unsupported',
    supportConflicting: 'conflicting',
    supportNotChecked: 'not checked',
    relevanceLabel: 'Relevance to the question (mechanical screening)',
    relRelevant: 'relevant',
    relPartial: 'partially relevant',
    relIrrelevant: 'not relevant',
    relUncertain: 'uncertain',
    relNotChecked: 'not checked',
    relatedTitle: 'Related documents (not used as evidence)',
    semLabel: 'Semantic check (automated screening)',
    semSupports: 'supports premise', semContradicts: 'contradicts premise', semMentionsOnly: 'mentions only',
    semInsufficient: 'no information', semUncertain: 'uncertain', semNotChecked: 'not checked',
    correctedTag: 'Premise corrected',
    correctionBasis: 'Correction basis (quoted from the source)',
    statusAnswerWithheld: 'The answer was withheld',
    compareTitle: 'Compare documents',
    compareDocA: 'Document A (library:record)',
    compareDocB: 'Document B (library:record)',
    compareAspects: 'Aspects (comma-separated)',
    compareButton: 'Compare',
    comparing: 'Comparing…',
    compareNotFound: 'No verified page found for this aspect',
    sharedTerms: 'Shared terms',
    uniqueTerms: 'Only in this document',
    langHintJa: 'Detected as a Japanese question',
    langHintEn: 'Detected as an English question (sources are searched across languages)',
  },
};

let lang = 'ja';
try { lang = localStorage.getItem('glm-lang') === 'en' ? 'en' : 'ja'; } catch (_) { lang = 'ja'; }
const t = () => I18N[lang];

function applyLang() {
  document.documentElement.lang = lang;
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (I18N[lang][key]) el.innerHTML = I18N[lang][key];
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.getAttribute('data-i18n-placeholder');
    if (I18N[lang][key]) el.setAttribute('placeholder', I18N[lang][key]);
  });
  langToggle.textContent = lang === 'ja' ? 'EN' : '日本語';
}

langToggle.addEventListener('click', () => {
  lang = lang === 'ja' ? 'en' : 'ja';
  try { localStorage.setItem('glm-lang', lang); } catch (_) { /* storage unavailable */ }
  applyLang();
});

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function safeHref(value) {
  try {
    const url = new URL(String(value));
    return url.protocol === 'https:' ? url.href : null;
  } catch (_) {
    return null;
  }
}

function sourceLink(value, label) {
  const href = safeHref(value);
  return href ? `<a class="source-link" href="${esc(href)}" target="_blank" rel="noreferrer noopener">${esc(label || t().backToSource)}</a>` : '';
}

function renderSearch(data) {
  const items = data.results || [];
  title.textContent = data.query ? t().recordsFor(data.query) : t().resultsTitle;
  const retrieved = data.retrieved_at ? new Date(data.retrieved_at) : null;
  const retrievedLabel = retrieved && !Number.isNaN(retrieved.valueOf()) ? retrieved.toLocaleString(lang === 'ja' ? 'ja-JP' : 'en-GB') : t().retrievedUnknown;
  meta.textContent = `${items.length}${t().countSuffix} · ${retrievedLabel}`;
  let html = items.map(item => `<article class="card" data-save-token="${esc(item.save_token || '')}"><div><span class="tag">${esc(item.library_name)}</span><h3>${esc(item.title)}</h3><p>${item.author ? esc(item.author) + ' · ' : ''}${item.date ? esc(item.date) : t().publishedUnknown}${item.language ? ' · ' + esc(item.language) : ''}</p><p>${esc(item.description || t().noDescription)}</p><p class="rights">${t().rightsLabel}: ${esc(item.rights?.statement || 'unknown')}</p></div><div>${sourceLink(item.landing_url)}</div></article>`).join('');
  if (data.errors?.length) html += data.errors.map(e => `<div class="error" role="alert">${esc(e.library_id)}: ${esc(e.error)}</div>`).join('');
  results.innerHTML = html || `<div class="empty"><span class="empty-mark">∅</span><p>${t().noMatches}</p></div>`;
}

function relevanceLabel(status) {
  return {relevant: t().relRelevant, partially_relevant: t().relPartial, irrelevant: t().relIrrelevant,
    uncertain: t().relUncertain, not_checked: t().relNotChecked}[status] || status || '';
}

function semanticsLine(item) {
  const sem = item.semantics;
  if (!sem || !sem.relation) return '';
  const label = {supports: t().semSupports, contradicts: t().semContradicts, mentions_only: t().semMentionsOnly,
    insufficient: t().semInsufficient, uncertain: t().semUncertain, not_checked: t().semNotChecked}[sem.relation] || sem.relation;
  const reasons = (sem.reasons || []).join(' / ');
  return `<p class="relevance-line">${t().semLabel}: <span class="badge badge-sem-${esc(sem.relation)}">${esc(label)}</span>`
    + (reasons ? ` <span class="relevance-reasons">${esc(reasons)}</span>` : '') + `</p>`;
}

function rankingReasonsLine(item) {
  const reasons = item.ranking_reasons || [];
  if (!reasons.length) return '';
  return `<p>${t().rankingReasonsLabel}: <span class="rel-reasons">${esc(reasons.join(' / '))}</span></p>`;
}

function relevanceLine(item) {
  const rel = item.relevance || (item.relevance_status ? {status: item.relevance_status, reasons: item.relevance_reasons || []} : null);
  if (!rel || !rel.status) return '';
  return `<p>${t().relevanceLabel}: <span class="badge badge-rel-${esc(rel.status)}">${esc(relevanceLabel(rel.status))}</span>`
    + (rel.score != null ? ` (${esc(rel.score)})` : '')
    + ((rel.reasons || []).length ? `<br><span class="rel-reasons">${esc(rel.reasons.join(' / '))}</span>` : '')
    + `</p>`;
}

function relatedCard(item) {
  return `<article class="card related-card">
    <div>
      <span class="tag">${esc(item.library_name || item.library_id || '')}</span>
      <h3>${esc(item.title || item.record_id || '')}</h3>
      ${relevanceLine(item)}
      ${rankingReasonsLine(item)}
      ${semanticsLine(item)}
    </div>
    <div class="card-actions">
      ${sourceLink(item.image_url, t().viewImage)}
      ${sourceLink(item.landing_url, t().viewRecord)}
    </div>
  </article>`;
}

function evidenceCard(item) {
  const excerpt = (item.ocr_text || '').slice(0, 300);
  const quality = item.ocr_quality?.score;
  const id = `ev-${CSS.escape(item.citation_key || '')}`;
  return `<article class="card evidence-card" id="${id}">
    <div>
      <span class="tag">${esc(item.library_name)}</span> <span class="badge badge-verified">${t().verifiedBadge}</span>
      <h3>${esc(item.title)}</h3>
      <p>${t().frameLabel} ${esc(item.digital_frame ?? 'unknown')} · ${t().qualityLabel} ${quality ?? 'unknown'} · ${t().matchedTermLabel}: ${esc(item.matched_term || '')}</p>
      ${relevanceLine(item)}
      ${rankingReasonsLine(item)}
      ${semanticsLine(item)}
      <p class="ocr-excerpt">${esc(excerpt)}</p>
      <p class="rights">${t().rightsLabel}: ${esc(item.rights?.statement || 'unknown')}</p>
      <div class="verify-box" data-page="${esc(item.page_id)}" data-library="${esc(item.library_id)}"></div>
    </div>
    <div class="card-actions">
      ${safeHref(item.image_url) ? `<a href="${esc(safeHref(item.image_url))}" target="_blank" rel="noreferrer noopener"><img class="evidence-thumb" src="${esc(safeHref(item.image_url))}" alt="" loading="lazy"></a>` : ''}
      ${sourceLink(item.image_url, t().viewImage)}
      ${sourceLink(item.landing_url, t().viewRecord)}
      <button type="button" class="verify-button">${t().verifyButton}</button>
    </div>
  </article>`;
}

function claimsSection(data) {
  const supportLabel = s => ({supported: t().supportSupported, uncertain: t().supportUncertain, unsupported: t().supportUnsupported, conflicting: t().supportConflicting, not_checked: t().supportNotChecked}[s] || s);
  if (!(data.claims || []).length) return '';
  return `<div class="claims"><h4>${t().claimsTitle}</h4><ul>`
    + data.claims.map(claim => `<li><span class="badge badge-${esc(claim.support || 'not_checked')}">${esc(supportLabel(claim.support))}</span> ${esc(claim.text)} `
      + (claim.citations || []).map(key => `<button type="button" class="chip chip-small" data-target="ev-${esc(key)}">${esc(key)}</button>`).join(' ')
      + `</li>`).join('')
    + `</ul></div>`;
}

function renderAnswer(data) {
  title.textContent = t().recordsFor(data.query || query.value.trim());
  const evidence = data.evidence || [];
  const unverified = data.unverified || [];
  meta.textContent = `${t().evidenceTitle}: ${evidence.length} · ${t().unverifiedTitle}: ${unverified.length}`;
  let html = '';
  if ((data.status === 'answered' || data.status === 'answered_partial') && data.answer) {
    const chips = (data.citations || []).map(c => `<button type="button" class="chip" data-target="ev-${esc(c.citation_key)}">${esc(c.title)} · ${t().frameLabel} ${esc(c.digital_frame ?? '?')}</button>`).join('');
    const badges = (data.provider === 'MockProvider' ? `<span class="tag demo-tag">${t().demoBadge}</span>` : '')
      + (data.status === 'answered_partial' ? `<span class="tag partial-tag">${t().partialTag}</span>` : '');
    html += `<article class="card answer-card"><div>${badges}<span class="tag">${t().answerTag}</span><h3>${esc(data.answer)}</h3>`
      + (chips ? `<p class="citations-label">${t().citationsLabel}</p><div class="chips">${chips}</div>` : '')
      + claimsSection(data)
      + ((data.limitations || []).length ? `<p class="rights">${t().limitationsLabel}: ${esc(data.limitations.join(' '))}</p>` : '')
      + `</div></article>`;
  } else if (data.status === 'corrected_premise' && data.answer) {
    const chips = (data.citations || []).map(c => `<button type="button" class="chip" data-target="ev-${esc(c.citation_key)}">${esc(c.title)} · ${t().frameLabel} ${esc(c.digital_frame ?? '?')}</button>`).join('');
    const quotes = (data.correction?.quotes || []).map(q => `<blockquote class="correction-quote">${esc(q)}</blockquote>`).join('');
    html += `<article class="card answer-card correction-card"><div><span class="tag">${t().correctedTag}</span><h3>${esc(data.answer)}</h3>`
      + (quotes ? `<p class="citations-label">${t().correctionBasis}</p>${quotes}` : '')
      + (chips ? `<p class="citations-label">${t().citationsLabel}</p><div class="chips">${chips}</div>` : '')
      + claimsSection(data)
      + ((data.limitations || []).length ? `<p class="rights">${t().limitationsLabel}: ${esc(data.limitations.join(' '))}</p>` : '')
      + `</div></article>`;
  } else if (data.status === 'insufficient_evidence') {
    html += `<div class="error" role="alert">${esc(data.reason || data.message || t().statusInsufficient)}</div>`
      + `<p class="rights">${t().budgetNote}</p>`;
  } else if (data.status === 'answer_withheld') {
    html += `<div class="error" role="alert">${t().statusAnswerWithheld}: ${esc(data.reason || '')}</div>` + claimsSection(data);
  } else if (data.status === 'citation_validation_failed') {
    html += `<div class="error" role="alert">${t().statusWithheld} ${esc(data.reason || '')}</div>`;
  } else {
    html += `<div class="error" role="alert">${t().statusUnavailable}: ${esc(data.reason || '')}</div>`;
  }
  html += evidence.map(evidenceCard).join('');
  const relatedItems = (data.related_documents && data.related_documents.length) ? data.related_documents : (data.related || []);
  if (relatedItems.length) {
    html += `<div class="related-box"><h4>${t().relatedTitle}</h4>` + relatedItems.map(relatedCard).join('') + `</div>`;
  }
  if (unverified.length) {
    html += `<div class="unverified-box"><h4>${t().unverifiedTitle}</h4><ul>`
      + unverified.map(u => `<li>${esc(u.library_id)} / ${esc(u.record_id)}${u.page_id ? ' / ' + esc(u.page_id) : ''} — ${esc(u.reason)}</li>`).join('')
      + `</ul></div>`;
  }
  if ((data.search?.errors || []).length) {
    html += data.search.errors.map(e => `<div class="error" role="alert">${esc(e.library_id)}: ${esc(e.error)}</div>`).join('');
  }
  results.innerHTML = html;
  results.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const target = document.getElementById(chip.getAttribute('data-target'));
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        target.classList.remove('flash');
        void target.offsetWidth;
        target.classList.add('flash');
      }
    });
  });
  results.querySelectorAll('.verify-button').forEach(button => {
    button.addEventListener('click', async () => {
      const box = button.closest('.evidence-card').querySelector('.verify-box');
      const { library, page } = box.dataset;
      button.disabled = true;
      box.innerHTML = `<p>${t().verifying}</p>`;
      try {
        const report = await fetchJson(`/api/verify?library=${encodeURIComponent(library)}&id=${encodeURIComponent(page)}`);
        const statusText = report.status === 'verified' ? t().verifyVerified : report.status === 'unsupported' ? t().verifyUnsupported : t().verifyFailed;
        const checks = report.checks ? `<ul class="checks">${Object.entries(report.checks).map(([name, check]) => `<li>${check.ok ? '✓' : '✗'} ${esc(name)} — ${esc(check.detail)}</li>`).join('')}</ul>` : `<p>${esc(report.reason || '')}</p>`;
        box.innerHTML = `<p class="verify-status">${esc(statusText)}</p>${checks}`;
      } catch (error) {
        box.innerHTML = `<p class="error">${esc(error.message)}</p>`;
      } finally {
        button.disabled = false;
      }
    });
  });
}

function selectedLibraries() {
  return [...form.querySelectorAll('input[name="library"]:checked')].map(i => i.value).join(',');
}

async function fetchJson(path, signal) {
  const response = await fetch(path, { signal });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || t().requestFailed);
  return data;
}

let activeController = null;
let currentOpId = null;
let serverCancelled = false;
const materialsResults = document.querySelector('#materials-results');
const cancelButton = document.querySelector('#cancel-button');
const stageStatus = document.querySelector('#stage-status');
const modeSelect = document.querySelector('#mode-select');
if (cancelButton) {
  cancelButton.addEventListener('click', async () => {
    serverCancelled = false;
    if (currentOpId) {
      try {
        const res = await fetchJson(`/api/cancel?op=${encodeURIComponent(currentOpId)}`);
        if (res.state === 'cancelled') serverCancelled = true;
      } catch (error) { /* fall through to local abort */ }
    }
    if (activeController) activeController.abort();
  });
}

function setBusy(busy) {
  searchButton.disabled = busy;
  answerButton.disabled = busy;
  results.setAttribute('aria-busy', String(busy));
}

// b7 (section 35): the structured conditions are built once and
// sent to BOTH the stage-1 bibliographic search and the materials
// investigation, so the two stages can no longer diverge.
function structuredParams() {
  const extra = new URLSearchParams();
  const authorVal = document.querySelector('#author-input');
  const titleVal = document.querySelector('#title-input');
  const yearFrom = document.querySelector('#year-from');
  const yearTo = document.querySelector('#year-to');
  if (authorVal && authorVal.value.trim()) extra.set('author', authorVal.value.trim());
  if (titleVal && titleVal.value.trim()) extra.set('title', titleVal.value.trim());
  if (yearFrom && yearFrom.value) extra.set('year_from', yearFrom.value);
  if (yearTo && yearTo.value) extra.set('year_to', yearTo.value);
  const doclangs = [...document.querySelectorAll('input[name="doclang"]:checked')].map(el => el.value);
  if (doclangs.length) extra.set('languages', doclangs.join(','));
  const expandMulti = document.querySelector('#expand-multi');
  const expandHist = document.querySelector('#expand-hist');
  if (expandMulti && !expandMulti.checked) extra.set('expand', '0');
  if (expandHist && !expandHist.checked) extra.set('historical', '0');
  const ocrReq = document.querySelector('#ocr-required');
  if (ocrReq && ocrReq.checked) extra.set('ocr', '1');
  return extra;
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const q = query.value.trim();
  if (!q) return;
  setBusy(true);
  results.innerHTML = `<div class="empty"><p>${t().searching}</p></div>`;
  notice.textContent = t().searchingNotice;
  try {
    const extraQs = structuredParams().toString();
    renderSearch(await fetchJson(`/api/search?q=${encodeURIComponent(q)}&libraries=${encodeURIComponent(selectedLibraries())}${extraQs ? `&${extraQs}` : ''}`));
    if (stageStatus) stageStatus.textContent = t().stageSearchDone;
  } catch (error) {
    results.innerHTML = `<div class="error" role="alert">${esc(error.message)}</div>`;
  } finally {
    setBusy(false);
  }
});

answerButton.addEventListener('click', async () => {
  const q = query.value.trim();
  if (!q) return;
  setBusy(true);
  answerButton.textContent = t().answering;
  results.innerHTML = `<div class="empty"><p>${t().answering}</p></div>`;
  try {
    renderAnswer(await fetchJson(`/api/answer?q=${encodeURIComponent(q)}&libraries=${encodeURIComponent(selectedLibraries())}`));
  } catch (error) {
    results.innerHTML = `<div class="error" role="alert">${esc(error.message)}</div>`;
  } finally {
    setBusy(false);
    answerButton.textContent = t().answerButton;
  }
});

function stateChips(states) {
  if (!states) return '';
  const chips = [];
  if (states.discovered) chips.push(t().stateDiscovered);
  if (states.accessible) chips.push(t().stateAccessible);
  if (states.source_verified) chips.push(t().stateVerified);
  if (states.relevant_candidate) chips.push(t().stateCandidate);
  if (states.assessed_evidence) chips.push(t().stateAssessed);
  if (states.rejected_for_answer) chips.push(t().stateRejected);
  return chips.map(c => `<span class="chip static">${esc(c)}</span>`).join('');
}

let lastMaterials = null;
let materialsAdmittedOnly = false;

function citationText(item) {
  const parts = [item.title || item.record_id, item.author, item.date,
    `${item.library_id}:${item.record_id}${item.page_id ? ':' + item.page_id : ''}`,
    item.landing_url || item.image_url || ''].filter(Boolean);
  return parts.join('. ');
}

function accessChips(item) {
  const a = item.access_state;
  if (!a) return '';
  const mark = (on) => (on ? '✓' : '–');
  const parts = [
    `${mark(a.bibliographic)} ${t().accessBiblio}`,
    `${mark(a.ocr_fetched)} ${t().accessOcr}`,
    `${mark(a.mapping_confirmed)} ${t().accessMapping}`,
    `${mark(a.passage_found)} ${t().accessPassage}`,
    `${mark(a.assessed_as_evidence)} ${t().accessAssessed}`,
  ];
  return `<p class="meta-line">${parts.join(' · ')}</p>`;
}

function renderMaterials(data) {
  lastMaterials = data;
  title.textContent = t().materialsTitle;
  const all = data.materials || [];
  const items = materialsAdmittedOnly ? all.filter(i => i.admitted_as_evidence) : all;
  meta.textContent = `${items.length}${t().countSuffix}`;
  let html = `<div class="notice">${esc(data.note || t().materialsNote)}</div>`
    + `<label class="filter-toggle"><input type="checkbox" id="materials-admitted-only" ${materialsAdmittedOnly ? 'checked' : ''}> ${t().admittedOnly}</label>`;
  if (data.discovery) {
    const d = data.discovery;
    // Final review (section 14): planned and executed variants
    // are different things - mark each planned variant with its
    // execution state instead of implying all of them ran.
    const executedSet = new Set(d.executed_variants || []);
    const variantLines = (d.planned_variants || []).map(v => `<li>${esc(v.text)} <span class="meta-line">[${esc(v.language)} · ${esc(v.kind)}] ${esc(v.reason || '')} · ${executedSet.has(v.text) ? t().variantExecuted : t().variantNotExecuted}</span></li>`).join('');
    const ambiguous = (d.ambiguous_authors || []).length ? `<p class="rights">${t().ambiguousAuthorLabel}: ${esc(d.ambiguous_authors.join(', '))}</p>` : '';
    const routingSkipped = Object.entries(d.routing_skipped || {}).map(([lib, why]) => `<p class="rights">${esc(lib)}: ${esc(why)}</p>`).join('');
    html += `<div class="notice" id="discovery-panel"><strong>${t().discoveryTitle}</strong>`
      + `<p class="meta-line">${t().queryLanguageLabel}: ${esc((d.query_language || {}).language || 'unknown')}</p>`
      + (variantLines ? `<ul>${variantLines}</ul>` : '') + ambiguous + routingSkipped + `</div>`;
  }
  for (const item of items) {
    const excerpts = (item.excerpts || []).map(p => `<blockquote class="correction-quote">${esc(p.text)}</blockquote>`).join('');
    const reasons = (item.not_admitted_reasons || []).length
      ? `<p class="rights">${t().notAdmittedLabel}: ${esc(item.not_admitted_reasons.join(' / '))}</p>` : '';
    const image = item.image_url ? `<p>${sourceLink(item.image_url, t().backToSource)}</p>` : '';
    const landing = item.landing_url ? `<p>${sourceLink(item.landing_url, t().sourcePage)}</p>` : '';
    const copyBtn = `<p><button type="button" class="copy-citation" data-citation="${esc(citationText(item))}">${t().copyCitation}</button></p>`;
    const rights = item.rights && (item.rights.status || item.rights.label)
      ? `<p class="rights">${t().rightsLabel}: ${esc(item.rights.status || item.rights.label)}</p>` : '';
    const discoveryBits = [];
    if (item.matched_variant) discoveryBits.push(`${t().matchedVariantLabel}: ${esc(item.matched_variant)}`);
    if (item.work_link && item.work_link.work_id) discoveryBits.push(`${t().workLinkLabel}: ${esc(item.work_link.work_id)}`);
    if (item.duplicate_group) discoveryBits.push(`${t().dupGroupLabel}: ${esc(item.duplicate_group.relation)}`);
    const discoveryLine = discoveryBits.length ? `<p class="meta-line">${discoveryBits.join(' · ')}</p>` : '';
    const discoveryReasons = (item.discovery_reasons || []).length
      ? `<p class="rights">${t().discoveryReasonsLabel}: ${esc(item.discovery_reasons.join(' / '))}</p>` : '';
    const bsbBtn = item.bsb_handoff && item.bsb_handoff.bsb_object_id
      ? `<p><button type="button" class="bsb-open" data-bsb-id="${esc(item.bsb_handoff.bsb_object_id)}">${t().bsbHandoffLabel} (${esc(item.bsb_handoff.bsb_object_id)})</button></p>` : '';
    html += `<article class="card" data-save-token="${esc(item.save_token || '')}"><div><h3>${esc(item.title || item.record_id)}</h3>`
      + `<p class="meta-line">${esc(item.author || '')} ${esc(item.date || '')} · ${esc(item.library_id)}:${esc(item.record_id)}${item.page_id ? ' · ' + esc(item.page_id) : ''}</p>`
      + `<div class="chips">${stateChips(item.states)}</div>`
      + accessChips(item)
      + (excerpts ? `<p class="citations-label">${t().excerptsLabel}</p>${excerpts}` : '')
      + discoveryLine + discoveryReasons + bsbBtn
      + reasons + rights + image + landing + copyBtn
      + `</div></article>`;
  }
  (materialsResults || results).innerHTML = html || `<div class="empty"><p>${t().noMatches}</p></div>`;
}

[results, materialsResults].forEach((el) => { if (el) el.addEventListener('click', (event) => {
  const btn = event.target && event.target.closest ? event.target.closest('.bsb-open') : null;
  if (!btn) return;
  const libSel = document.querySelector('#lookup-library');
  const recInput = document.querySelector('#lookup-record');
  const docBtn = document.querySelector('#lookup-document-button');
  if (libSel && recInput && docBtn) {
    libSel.value = 'bsb';
    recInput.value = btn.dataset.bsbId || '';
    docBtn.click();
  }
}); });

[results, materialsResults].forEach((el) => { if (el) el.addEventListener('change', (event) => {
  if (event.target && event.target.id === 'materials-admitted-only') {
    materialsAdmittedOnly = event.target.checked;
    if (lastMaterials) renderMaterials(lastMaterials);
  }
}); });
[results, materialsResults].forEach((el) => { if (el) el.addEventListener('click', async (event) => {
  const btn = event.target.closest ? event.target.closest('.copy-citation') : null;
  if (!btn) return;
  try {
    await navigator.clipboard.writeText(btn.dataset.citation || '');
    btn.textContent = t().copied;
  } catch (error) {
    btn.textContent = btn.dataset.citation || '';
  }
}); });

materialsButton.addEventListener('click', async () => {
  const q = query.value.trim();
  if (!q) return;
  setBusy(true);
  serverCancelled = false;
  currentOpId = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : `op-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  if (cancelButton) cancelButton.hidden = false;
  if (stageStatus) stageStatus.textContent = t().statusRunning;
  (materialsResults || results).innerHTML = `<div class="empty"><p>${t().searching}</p></div>`;
  activeController = new AbortController();
  try {
    const mode = modeSelect ? modeSelect.value : 'standard';
    const extraQs = structuredParams().toString() ? `&${structuredParams().toString()}` : '';
    const data = await fetchJson(`/api/materials?q=${encodeURIComponent(q)}&libraries=${encodeURIComponent(selectedLibraries())}&mode=${encodeURIComponent(mode)}&op=${encodeURIComponent(currentOpId)}${extraQs}`, activeController.signal);
    if (data.op_state === 'cancelled') {
      if (stageStatus) stageStatus.textContent = t().statusCancelled;
      (materialsResults || results).innerHTML = `<div class="empty"><p>${t().statusCancelled}</p></div>`;
      return;
    }
    if (data.op_state === 'timeout') {
      if (stageStatus) stageStatus.textContent = t().statusTimeout;
      (materialsResults || results).innerHTML = `<div class="empty"><p>${t().statusTimeout}</p></div>`;
      return;
    }
    renderMaterials(data);
    const partial = (data.errors && data.errors.length) || (data.stage_log || []).some(s => s.status === 'early_stop' || s.status === 'deadline' || s.status === 'failed');
    if (window.glmWorkspace) window.glmWorkspace.recordHistory(data, q, mode, partial ? 'partial' : 'completed');
    if (stageStatus) {
      const perf = data.timings && data.http_stats ? ` ${t().perfSummary(data.timings.total_s ?? '?', data.http_stats.requests ?? '?')}` : '';
      stageStatus.textContent = (partial ? t().statusPartial : t().statusComplete) + perf;
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      // Show "cancelled" only when the server confirmed the stop.
      if (stageStatus) stageStatus.textContent = serverCancelled ? t().statusCancelled : t().statusCancelRequested;
      (materialsResults || results).innerHTML = `<div class="empty"><p>${esc(stageStatus ? stageStatus.textContent : '')}</p></div>`;
    } else {
      if (stageStatus) stageStatus.textContent = t().statusFailed;
      (materialsResults || results).innerHTML = `<div class="error" role="alert">${esc(error.message)}</div>`;
    }
  } finally {
    activeController = null;
    currentOpId = null;
    if (cancelButton) cancelButton.hidden = true;
    setBusy(false);
  }
});

const langHint = document.querySelector('#lang-hint');
query.addEventListener('input', () => {
  const value = query.value;
  if (/[ぁ-んァ-ヶ一-龥]/.test(value)) langHint.textContent = t().langHintJa;
  else if (/[A-Za-z]{2,}/.test(value)) langHint.textContent = t().langHintEn;
  else langHint.textContent = '';
});

const compareForm = document.querySelector('#compare-form');
const compareResults = document.querySelector('#compare-results');
const compareButton = document.querySelector('#compare-button');

function renderCompare(data) {
  if (data.status !== 'compared') {
    compareResults.innerHTML = `<div class="error" role="alert">${esc(data.reason || t().statusInsufficient)}</div>`;
    return;
  }
  const docs = data.documents || [];
  let html = `<div class="compare-docs">${docs.map(d => `<div class="compare-doc"><strong>${esc(d.title)}</strong><br>${esc(d.library_id)}:${esc(d.record_id)} · ${esc(d.date ?? 'unknown')} · ${t().evidenceTitle}: ${d.verified_pages}${d.error ? `<br><span class="error">${esc(d.error)}</span>` : ''}</div>`).join('')}</div>`;
  for (const row of data.rows || []) {
    html += `<div class="compare-row"><h3>${esc(row.aspect)}</h3><div class="compare-sides">`;
    for (const d of docs) {
      const side = (row.documents || {})[`${d.library_id}|${d.record_id}`] || (row.documents || {})[d.record_id] || {found: false, excerpts: []};
      html += `<div class="compare-side"><h4>${esc(d.title)}</h4>`;
      if (!side.found) html += `<p class="rights">${t().compareNotFound}</p>`;
      for (const ex of side.excerpts || []) {
        html += `<blockquote class="compare-excerpt">${esc(ex.excerpt)}<footer>${esc(ex.citation_key)}${safeHref(ex.image_url) ? ` · <a href="${esc(safeHref(ex.image_url))}" target="_blank" rel="noreferrer noopener">${t().viewImage}</a>` : ''}</footer></blockquote>`;
      }
      const unique = (row.unique_terms || {})[`${d.library_id}|${d.record_id}`] || (row.unique_terms || {})[d.record_id] || [];
      if (unique.length) html += `<p class="rights">${t().uniqueTerms}: ${unique.map(esc).join('、')}</p>`;
      html += `</div>`;
    }
    html += `</div>`;
    if ((row.shared_terms || []).length) html += `<p class="rights">${t().sharedTerms}: ${row.shared_terms.map(esc).join('、')}</p>`;
    html += `</div>`;
  }
  if ((data.notes || []).length) html += `<div class="unverified-box"><ul>${data.notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul></div>`;
  compareResults.innerHTML = html;
}

compareForm.addEventListener('submit', async event => {
  event.preventDefault();
  const a = document.querySelector('#cmp-a').value.trim();
  const b = document.querySelector('#cmp-b').value.trim();
  const aspects = document.querySelector('#cmp-aspects').value.trim();
  if (!a || !b) return;
  compareButton.disabled = true;
  compareResults.innerHTML = `<div class="empty"><p>${t().comparing}</p></div>`;
  try {
    const params = new URLSearchParams({docs: `${a};${b}`, aspects});
    renderCompare(await fetchJson(`/api/compare?${params.toString()}`));
  } catch (error) {
    compareResults.innerHTML = `<div class="error" role="alert">${esc(error.message)}</div>`;
  } finally {
    compareButton.disabled = false;
  }
});

// ---- Library directory (b5, section 16): registry-driven, with
// region/language filters and per-capability verification status.
const librariesList = document.querySelector('#libraries-list');
const libRegion = document.querySelector('#lib-region');
const libLang = document.querySelector('#lib-lang');
const libOcrOnly = document.querySelector('#lib-ocr-only');
let allLibraries = [];

function renderLibraries() {
  if (!librariesList) return;
  const region = libRegion?.value || '';
  const lang = libLang?.value || '';
  const ocrOnly = libOcrOnly?.checked || false;
  const items = allLibraries.filter(item => {
    if (region && item.region !== region) return false;
    if (lang && !(item.languages || []).includes(lang)) return false;
    if (ocrOnly && (item.capability_status?.page_ocr || '') !== 'live_page_verified') return false;
    return true;
  });
  librariesList.innerHTML = items.map(item => {
    const caps = Object.entries(item.capability_status || {}).map(([k, v]) => `<span class="tag">${esc(k)}: ${esc(v)}</span>`).join(' ');
    const status = item.implementation_status === 'implemented' ? t().implementedLabel : t().researchOnlyLabel;
    return `<article class="card"><div><span class="tag">${esc(status)}</span><h3>${esc(item.name || item.id)}</h3><p>${esc(item.region || '')} · ${esc(item.country || '')} · ${(item.languages || []).map(esc).join(', ')}</p><p>${caps}</p>${item.auth ? `<p class="meta-line">${esc(item.auth)}</p>` : ''}<p class="rights">${esc(item.verification || '')}</p></div><div>${safeHref(item.official_site) ? `<a class="source-link" href="${esc(safeHref(item.official_site))}" target="_blank" rel="noreferrer noopener">${esc(t().officialSiteLabel)} ↗</a>` : ''}</div></article>`;
  }).join('') || '<div class="empty"><p>—</p></div>';
}

// --- ID-addressed lookup (b5 final review, S18) -----------------
const lookupLibrary = document.querySelector('#lookup-library');
const lookupRecord = document.querySelector('#lookup-record');
const lookupPage = document.querySelector('#lookup-page');
const lookupQuery = document.querySelector('#lookup-query');
const lookupResults = document.querySelector('#lookup-results');

function renderLookup(data, kind) {
  if (!lookupResults) return;
  if (data.error) {
    lookupResults.innerHTML = `<article class="card"><p>${esc(data.detail || data.error)}</p></article>`;
    return;
  }
  if (kind === 'document') {
    const rights = data.rights || {};
    const orgLines = [
      data.holding_institution ? `所蔵: ${data.holding_institution}` : '',
      data.provider ? `提供: ${data.provider}` : '',
      data.data_provider ? `提供: ${data.data_provider}` : '',
      data.aggregation_provider ? `集約: ${data.aggregation_provider}` : '',
      data.platform ? `プラットフォーム: ${data.platform}` : '',
    ].filter(Boolean).map(esc).join(' · ');
    const restrictions = (data.access_restrictions || []).map(esc).join(' / ');
    const handoffs = (data.handoff_candidates || []).length;
    lookupResults.innerHTML = `<article class="card" data-save-token="${esc(data.save_token || '')}"><div><span class="tag">${esc(data.library_id || '')}</span><h3>${esc(data.title || data.record_id || '')}</h3>`
      + `<p>${esc(data.author || '')} ${esc(data.date || '')}</p>`
      + (orgLines ? `<p class="meta-line">${orgLines}</p>` : '')
      + `<p class="rights">${t().rightsLabel}: ${esc(rights.statement || 'unknown')}${rights.classification ? ` · ${t().rightsClassLabel}: ${esc(rights.classification)}` : ''}</p>`
      + (restrictions ? `<p class="rights">${esc(restrictions)}</p>` : '')
      + (handoffs ? `<p class="meta-line">提供元への引き継ぎ候補: ${handoffs}件</p>` : '')
      + `<p>${data.page_count ? `${data.page_count} pages` : ''}</p></div><div>${sourceLink(data.landing_url)}</div></article>`;
    return;
  }
  if (kind === 'page') {
    const text = data.contents || '';
    lookupResults.innerHTML = `<article class="card" data-page-token="${esc(data.save_token || '')}" data-library="${esc(data.library_id || '')}" data-page-id="${esc(data.page_id || '')}"><div><span class="tag">${esc(data.library_id || '')}</span><h3>${esc(data.page_id || '')}</h3>`
      + `<p>${data.verified_mapping ? t().mappingVerified : t().mappingUnverified}</p>`
      + `<p>${esc(text.slice(0, 600))}</p></div><div>${sourceLink(data.image_url, t().viewImage)}${sourceLink(data.landing_url, t().viewRecord)}</div></article>`;
    return;
  }
  const list = (data.matches && data.matches.list) || [];
  const items = list.map(m => `<article class="card"><div><h3>${esc(m.page_id)}</h3><p>${esc(m.snippet || '')}</p><p>${m.mapping_status === 'verified' ? t().mappingVerified : t().mappingUnverified}</p></div></article>`).join('');
  lookupResults.innerHTML = `<p>${t().coverageLabel}: ${data.pages_searched ?? ''}/${data.total_pages ?? ''} pages${data.complete ? '' : ' (partial)'}</p>` + (items || `<p>${esc(data.note || '')}</p>`);
}

async function runLookup(kind) {
  if (!lookupLibrary) return;
  const library = lookupLibrary.value;
  const record = (lookupRecord.value || '').trim();
  const page = (lookupPage.value || '').trim();
  const query = (lookupQuery.value || '').trim();
  let url = '';
  if (kind === 'document') url = `/api/document?library=${encodeURIComponent(library)}&id=${encodeURIComponent(record)}`;
  if (kind === 'page') url = `/api/page?library=${encodeURIComponent(library)}&id=${encodeURIComponent(page || record)}`;
  if (kind === 'search') url = `/api/in-document?library=${encodeURIComponent(library)}&id=${encodeURIComponent(record)}&q=${encodeURIComponent(query)}`;
  lookupResults.innerHTML = '';
  try {
    const response = await fetch(url);
    renderLookup(await response.json(), kind);
  } catch (error) {
    renderLookup({ error: 'fetch failed', detail: String(error) }, kind);
  }
}

for (const [id, kind] of [['#lookup-document-button', 'document'], ['#lookup-page-button', 'page'], ['#lookup-search-button', 'search']]) {
  const button = document.querySelector(id);
  if (button) button.addEventListener('click', () => runLookup(kind));
}

async function loadLibraries() {
  if (!librariesList) return;
  try {
    const data = await fetchJson('/api/libraries');
    allLibraries = data.libraries || [];
    const regions = [...new Set(allLibraries.map(i => i.region).filter(Boolean))].sort();
    const langs = [...new Set(allLibraries.flatMap(i => i.languages || []))].sort();
    for (const r of regions) { const o = document.createElement('option'); o.value = r; o.textContent = r; libRegion.appendChild(o); }
    for (const l of langs) { const o = document.createElement('option'); o.value = l; o.textContent = l; libLang.appendChild(o); }
    renderLibraries();
  } catch (error) { /* directory is informational; search keeps working */ }
}
libRegion?.addEventListener('change', renderLibraries);
libLang?.addEventListener('change', renderLibraries);
libOcrOnly?.addEventListener('change', renderLibraries);
loadLibraries();

// b10 (section 37): state the actually-active search features in
// the results header. If the endpoint fails, show nothing - never
// guess that semantic search is available.
async function loadFeatures() {
  const meta = document.querySelector('#result-meta');
  if (!meta) return;
  try {
    const features = await fetchJson('/api/features');
    meta.textContent = t().featuresLine(features);
  } catch (error) { /* informational only */ }
}
loadFeatures();

applyLang();
