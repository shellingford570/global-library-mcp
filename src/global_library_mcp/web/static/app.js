const form = document.querySelector('#search-form');
const query = document.querySelector('#query');
const results = document.querySelector('#results');
const title = document.querySelector('#result-title');
const meta = document.querySelector('#result-meta');
const notice = document.querySelector('#notice');
const answerButton = document.querySelector('#answer-button');
const searchButton = form.querySelector('button[type="submit"]');
const langToggle = document.querySelector('#lang-toggle');

const I18N = {
  ja: {
    status: 'OCR根拠つき回答 / 検証済み原本',
    h1: '世界の原資料へ、<em>検証可能な経路</em>で。',
    lede: '図書館とデジタルアーカイブを横断検索し、実際のOCR本文を根拠として回答します。引用は原本ページで検証でき、未確認の情報は隠さず表示します。',
    queryLabel: '調べたいこと',
    queryPlaceholder: '例：明治時代の日本の発電技術',
    searchButton: '検索する',
    answerButton: 'AI回答',
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
    lede: 'Search libraries and digital archives together and answer from actual OCR page text. Every citation can be checked against the original page, and unverified information is shown, not hidden.',
    queryLabel: 'What do you want to research?',
    queryPlaceholder: 'e.g. hydroelectric power in Meiji-era Japan',
    searchButton: 'Search',
    answerButton: 'AI answer',
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
  let html = items.map(item => `<article class="card"><div><span class="tag">${esc(item.library_name)}</span><h3>${esc(item.title)}</h3><p>${item.author ? esc(item.author) + ' · ' : ''}${item.date ? esc(item.date) : t().publishedUnknown}</p><p>${esc(item.description || t().noDescription)}</p><p class="rights">${t().rightsLabel}: ${esc(item.rights?.statement || 'unknown')}</p></div><div>${sourceLink(item.landing_url)}</div></article>`).join('');
  if (data.errors?.length) html += data.errors.map(e => `<div class="error" role="alert">${esc(e.library_id)}: ${esc(e.error)}</div>`).join('');
  results.innerHTML = html || `<div class="empty"><span class="empty-mark">∅</span><p>${t().noMatches}</p></div>`;
}

function relevanceLabel(status) {
  return {relevant: t().relRelevant, partially_relevant: t().relPartial, irrelevant: t().relIrrelevant,
    uncertain: t().relUncertain, not_checked: t().relNotChecked}[status] || status || '';
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
  if (data.status === 'answered' && data.answer) {
    const chips = (data.citations || []).map(c => `<button type="button" class="chip" data-target="ev-${esc(c.citation_key)}">${esc(c.title)} · ${t().frameLabel} ${esc(c.digital_frame ?? '?')}</button>`).join('');
    html += `<article class="card answer-card"><div><span class="tag">${t().answerTag}</span><h3>${esc(data.answer)}</h3>`
      + (chips ? `<p class="citations-label">${t().citationsLabel}</p><div class="chips">${chips}</div>` : '')
      + claimsSection(data)
      + ((data.limitations || []).length ? `<p class="rights">${t().limitationsLabel}: ${esc(data.limitations.join(' '))}</p>` : '')
      + `</div></article>`;
  } else if (data.status === 'insufficient_evidence') {
    html += `<div class="error" role="alert">${esc(data.reason || data.message || t().statusInsufficient)}</div>`;
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

async function fetchJson(path) {
  const response = await fetch(path);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || t().requestFailed);
  return data;
}

function setBusy(busy) {
  searchButton.disabled = busy;
  answerButton.disabled = busy;
  results.setAttribute('aria-busy', String(busy));
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const q = query.value.trim();
  if (!q) return;
  setBusy(true);
  results.innerHTML = `<div class="empty"><p>${t().searching}</p></div>`;
  notice.textContent = t().searchingNotice;
  try {
    renderSearch(await fetchJson(`/api/search?q=${encodeURIComponent(q)}&libraries=${encodeURIComponent(selectedLibraries())}`));
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
      const side = (row.documents || {})[d.record_id] || {found: false, excerpts: []};
      html += `<div class="compare-side"><h4>${esc(d.title)}</h4>`;
      if (!side.found) html += `<p class="rights">${t().compareNotFound}</p>`;
      for (const ex of side.excerpts || []) {
        html += `<blockquote class="compare-excerpt">${esc(ex.excerpt)}<footer>${esc(ex.citation_key)}${safeHref(ex.image_url) ? ` · <a href="${esc(safeHref(ex.image_url))}" target="_blank" rel="noreferrer noopener">${t().viewImage}</a>` : ''}</footer></blockquote>`;
      }
      const unique = (row.unique_terms || {})[d.record_id] || [];
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

applyLang();
