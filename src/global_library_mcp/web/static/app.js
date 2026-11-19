const form = document.querySelector('#search-form');
const query = document.querySelector('#query');
const results = document.querySelector('#results');
const title = document.querySelector('#result-title');
const meta = document.querySelector('#result-meta');
const notice = document.querySelector('#notice');
const answerButton = document.querySelector('#answer-button');
const searchButton = form.querySelector('button[type="submit"]');

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

function sourceLink(value) {
  const href = safeHref(value);
  return href ? `<a class="source-link" href="${esc(href)}" target="_blank" rel="noreferrer noopener">原本へ戻る ↗</a>` : '';
}

function render(data) {
  const items = data.results || [];
  title.textContent = data.query ? `「${data.query}」の記録` : '検索結果';
  const retrieved = data.retrieved_at ? new Date(data.retrieved_at) : null;
  const retrievedLabel = retrieved && !Number.isNaN(retrieved.valueOf()) ? retrieved.toLocaleString('ja-JP') : '取得時刻 unknown';
  meta.textContent = `${items.length}件 · ${retrievedLabel}`;
  let html = items.map(item => `<article class="card"><div><span class="tag">${esc(item.library_name)}</span><h3>${esc(item.title)}</h3><p>${item.author ? esc(item.author) + ' · ' : ''}${item.date ? esc(item.date) : '出版年 unknown'}</p><p>${esc(item.description || '資料の詳細説明は提供されていません。')}</p><p class="rights">権利: ${esc(item.rights?.statement || 'unknown')}</p></div><div>${sourceLink(item.landing_url)}</div></article>`).join('');
  if (data.errors?.length) html += data.errors.map(e => `<div class="error" role="alert">${esc(e.library_id)}: ${esc(e.error)}</div>`).join('');
  results.innerHTML = html || '<div class="empty"><span class="empty-mark">∅</span><p>一致する記録は見つかりませんでした。検索語を変えて試してください。</p></div>';
}

function selectedLibraries() {
  return [...form.querySelectorAll('input[name="library"]:checked')].map(i => i.value).join(',');
}

async function fetchJson(path) {
  const response = await fetch(path);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'リクエストに失敗しました');
  return data;
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const q = query.value.trim();
  if (!q) return;
  searchButton.disabled = true;
  answerButton.disabled = true;
  results.setAttribute('aria-busy', 'true');
  results.innerHTML = '<div class="empty"><p>各機関へ問い合わせています…</p></div>';
  notice.textContent = 'ライブAPIの応答を統合しています。機関ごとの失敗は部分結果とともに表示されます。';
  try {
    render(await fetchJson(`/api/search?q=${encodeURIComponent(q)}&libraries=${encodeURIComponent(selectedLibraries())}`));
  } catch (error) {
    results.innerHTML = `<div class="error" role="alert">${esc(error.message)}</div>`;
  } finally {
    searchButton.disabled = false;
    answerButton.disabled = false;
    results.setAttribute('aria-busy', 'false');
  }
});

answerButton.addEventListener('click', async () => {
  const q = query.value.trim();
  if (!q) return;
  answerButton.disabled = true;
  searchButton.disabled = true;
  results.setAttribute('aria-busy', 'true');
  answerButton.textContent = '回答を生成中…';
  try {
    const data = await fetchJson(`/api/answer?q=${encodeURIComponent(q)}&libraries=${encodeURIComponent(selectedLibraries())}`);
    if (data.answer) {
      const citations = Array.isArray(data.citations) ? `引用: ${data.citations.join(', ')}` : '';
      results.innerHTML = `<article class="card"><div><span class="tag">EVIDENCE ANSWER</span><h3>${esc(data.answer)}</h3><p>${esc((data.limitations || []).join(' '))}</p><p class="rights">${esc(citations)}</p></div><div><span class="source-link">${data.available ? 'LLM provider' : '検索結果のみ'}</span></div></article>`;
      (data.search?.results || []).forEach(item => { results.insertAdjacentHTML('beforeend', `<article class="card"><div><span class="tag">${esc(item.library_name)}</span><h3>${esc(item.title)}</h3><p>${esc(item.description || '')}</p></div><div>${sourceLink(item.landing_url)}</div></article>`); });
    } else {
      render(data.search || {query: q, results: [], errors: []});
      results.insertAdjacentHTML('afterbegin', `<div class="error" role="alert">AI回答は利用できません: ${esc(data.reason || '根拠不足')}</div>`);
    }
  } catch (error) {
    results.innerHTML = `<div class="error" role="alert">${esc(error.message)}</div>`;
  } finally {
    answerButton.disabled = false;
    searchButton.disabled = false;
    answerButton.textContent = 'AI回答';
    results.setAttribute('aria-busy', 'false');
  }
});
