// Research Workspace client (b7). Active only when the server
// enabled the workspace (meta glm-workspace=1). All stored
// content is rendered with textContent / DOM APIs - never as
// HTML - so saved notes, OCR text and imported data cannot
// become stored XSS.
(function () {
  const enabled = document.querySelector('meta[name="glm-workspace"]')?.content === '1';
  if (!enabled) return;
  const csrf = document.querySelector('meta[name="glm-csrf"]')?.content || '';
  const section = document.getElementById('workspace-section');
  const panel = document.getElementById('ws-panel');
  const status = document.getElementById('ws-status');
  const select = document.getElementById('ws-project-select');
  section.hidden = false;
  let projectId = localStorage.getItem('glm-ws-project') || '';
  let currentTab = 'documents';
  let compareSelection = new Set();

  function say(message) { status.textContent = message; }

  async function wsFetch(path, options = {}) {
    const method = options.method || 'GET';
    const headers = { ...(options.headers || {}) };
    if (method !== 'GET') headers['X-GLM-CSRF'] = csrf;
    let body = options.body;
    if (body !== undefined && !(body instanceof ArrayBuffer)) {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(body);
    }
    const res = await fetch(path, { method, headers, body });
    const text = await res.text();
    let data = null;
    try { data = JSON.parse(text); } catch { data = null; }
    if (!res.ok) {
      const err = new Error((data && data.error) || `HTTP ${res.status}`);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return options.raw ? text : data;
  }

  // Delete with the server's related-record preview: a first
  // DELETE returns 409 + counts when related records exist;
  // only after the user confirms those exact counts do we
  // retry with confirm=1.
  async function deleteWithPreview(path, label) {
    try {
      await wsFetch(path, { method: 'DELETE' });
      return true;
    } catch (e) {
      if (e.status !== 409 || !e.data?.related_counts) throw e;
      const c = e.data.related_counts;
      const summary = Object.entries(c).map(([k, v]) => `${k}: ${v}`).join(' / ');
      if (!confirm(`${label}\n関連レコード: ${summary}\n${e.data.note || ''}\n続行しますか？`)) return false;
      await wsFetch(`${path}?confirm=1`, { method: 'DELETE' });
      return true;
    }
  }

  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function button(label, onClick) {
    const b = el('button', label);
    b.type = 'button';
    b.addEventListener('click', onClick);
    return b;
  }

  // ---- projects ------------------------------------------------------
  async function loadProjects() {
    const data = await wsFetch('/api/workspace/projects');
    select.innerHTML = '';
    for (const p of data.projects) {
      const opt = document.createElement('option');
      opt.value = p.project_id;
      opt.textContent = `${p.title}（資料${p.counts.documents}・引用${p.counts.citations}・ノート${p.counts.notes}）`;
      select.appendChild(opt);
    }
    if (![...select.options].some(o => o.value === projectId)) {
      projectId = select.options[0]?.value || '';
    }
    select.value = projectId;
    localStorage.setItem('glm-ws-project', projectId);
    const st = await wsFetch('/api/workspace/status');
    document.getElementById('ws-db-path').textContent = st.db_path || '';
    renderTab();
  }
  select.addEventListener('change', () => {
    projectId = select.value;
    localStorage.setItem('glm-ws-project', projectId);
    compareSelection.clear();
    renderTab();
  });
  document.getElementById('ws-create-project').addEventListener('click', async () => {
    const input = document.getElementById('ws-new-project-title');
    const title = input.value.trim();
    if (!title) return;
    try {
      const p = await wsFetch('/api/workspace/projects', { method: 'POST', body: { title } });
      projectId = p.project_id;
      input.value = '';
      say('プロジェクトを作成しました');
      await loadProjects();
    } catch (e) { say(e.message); }
  });

  // ---- save buttons injected into result cards ------------------------
  function injectButtons(root) {
    // the added node itself may be a card (innerHTML renders add
    // the article elements directly), so include it in the scan
    const cards = [...root.querySelectorAll('[data-save-token]')];
    if (root.matches && root.matches('[data-save-token]')) cards.unshift(root);
    cards.forEach(card => {
      const token = card.getAttribute('data-save-token');
      if (!token || card.querySelector('.ws-save-doc')) return;
      const b = button('プロジェクトへ保存', async () => {
        if (!projectId) { say('先にプロジェクトを作成してください'); return; }
        try {
          await wsFetch('/api/workspace/documents', { method: 'POST', body: { project_id: projectId, save_token: token } });
          b.textContent = '保存済み';
          b.disabled = true;
          say('資料を保存しました');
        } catch (e) { say(e.message); }
      });
      b.className = 'ws-save-doc';
      card.appendChild(b);
    });
    const pageCards = [...root.querySelectorAll('[data-page-token]')];
    if (root.matches && root.matches('[data-page-token]')) pageCards.unshift(root);
    pageCards.forEach(card => {
      const token = card.getAttribute('data-page-token');
      if (!token || card.querySelector('.ws-save-cite')) return;
      const b = button('引用を作成', () => {
        openCite(card.getAttribute('data-library') || '', card.getAttribute('data-page-id') || '', token);
      });
      b.className = 'ws-save-cite';
      card.appendChild(b);
    });
  }
  new MutationObserver(muts => muts.forEach(m => m.addedNodes.forEach(n => {
    if (n.nodeType === 1) injectButtons(n);
  }))).observe(document.body, { childList: true, subtree: true });

  // ---- tabs -------------------------------------------------------------
  document.querySelectorAll('[data-ws-tab]').forEach(b => {
    b.addEventListener('click', () => { currentTab = b.getAttribute('data-ws-tab'); renderTab(); });
  });

  function renderTab() {
    panel.innerHTML = '';
    if (!projectId) { panel.appendChild(el('p', 'プロジェクトを作成すると、資料・引用・ノートを保存できます。')); return; }
    ({ documents: renderDocuments, citations: renderCitations, notes: renderNotes,
       comparisons: renderComparisons, history: renderHistory, cite: renderCiteForm,
       export: renderExport, research: renderResearch }[currentTab] || renderDocuments)();
  }

  // ---- b11 research validation tab (sections 49-54) --------------------
  // State wording follows section 52: candidate/unconfirmed states
  // are NEVER shown with a green "verified" style; trust and state
  // are always rendered as text, and NLI/semantic scores are never
  // presented as probabilities of correctness.
  async function renderResearch() {
    const base = `/api/workspace/projects/${encodeURIComponent(projectId)}/research`;
    const progress = await wsFetch(`${base}/progress`);
    panel.appendChild(el('h3', '研究の進捗（候補ベース）'));
    const byKind = progress.b10_artefacts || {};
    const rows = [
      ['保存資料', progress.saved_documents],
      ['保存引用', progress.saved_citations],
      ['研究質問（サーバー生成）', byKind.b10_research_question || 0],
      ['主張評価（サーバー生成）', byKind.b10_claim_assessment || 0],
      ['根拠不足の主張', progress.claims_with_insufficient_evidence],
      ['矛盾候補', progress.contradiction_candidates],
      ['未検証の典拠候補', progress.unverified_authority_candidates],
      ['比較（サーバー生成）', byKind.b10_comparison || 0],
      ['時系列（サーバー生成）', byKind.b10_timeline || 0],
      ['レポート（サーバー生成）', byKind.b10_research_report || 0],
      ['意味検索の記録', byKind.b10_semantic_search || 0],
      ['未信頼の成果物（手動ノート等）', progress.untrusted_artefacts],
    ];
    const table = el('div');
    rows.forEach(([k, v]) => table.appendChild(el('p', `${k}: ${v}`)));
    panel.appendChild(table);

    const q = document.createElement('input');
    q.type = 'text'; q.placeholder = '研究質問を入力'; q.maxLength = 2000;
    panel.append(q, button('質問を構造化して保存', async () => {
      if (!q.value.trim()) return;
      const r = await wsFetch(`${base}/questions`, { method: 'POST', body: { question: q.value } });
      say(`質問を保存しました（意図: ${r.structured.research_intent || 'unknown'}）`);
      renderTab();
    }));

    const c = document.createElement('input');
    c.type = 'text'; c.placeholder = '主張を入力'; c.maxLength = 2000;
    panel.append(c, button('主張を構造化して保存', async () => {
      if (!c.value.trim()) return;
      const r = await wsFetch(`${base}/claims`, { method: 'POST', body: { statement: c.value } });
      const ex = r.claim.extraction || {};
      const missing = Object.entries(ex).filter(([, v]) => v === 'not_extracted').map(([k]) => k);
      say(`主張を保存しました（未抽出: ${missing.join(', ') || 'なし'}）`);
      renderTab();
    }));

    const graph = await wsFetch(`${base}/graph?limit=50`);
    panel.appendChild(el('h3', '根拠グラフ'));
    panel.appendChild(el('p', `ノード ${graph.node_count}件 / 辺 ${graph.edge_count}件（省略: ノード ${graph.omitted_nodes}件・辺 ${graph.omitted_edges}件）`));
    graph.edges.slice(0, 50).forEach(e => {
      panel.appendChild(el('p', `${e.source} —[${e.type} / ${e.state}]→ ${e.target}`));
    });

    const timeline = await wsFetch(`${base}/timeline`);
    panel.appendChild(el('h3', '時系列（順序は因果を示しません）'));
    (timeline.events || []).forEach(e => panel.appendChild(el('p', `${e.year} [${e.date_kind}] ${e.label}`)));
    if (!(timeline.events || []).length) panel.appendChild(el('p', '日付のある出来事はまだありません。'));

    panel.appendChild(el('h3', '研究レポート'));
    panel.append(button('レポートを生成', async () => {
      const rep = await wsFetch(`${base}/reports`, { method: 'POST', body: {} });
      say(`レポート ${rep.report_id} を生成しました（未解決参照 ${rep.unresolved_count}件）`);
      const pre = el('pre', rep.markdown);
      panel.appendChild(pre);
      const dl = (name, text, type) => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([text], { type }));
        a.download = name; a.textContent = name; panel.appendChild(a);
      };
      dl(`${rep.report_id}.md`, rep.markdown, 'text/markdown');
      dl(`${rep.report_id}.json`, JSON.stringify(rep, null, 1), 'application/json');
    }));
    panel.append(button('状態を再構築（原典の再取得はしません）', async () => {
      const r = await wsFetch(`${base}/refresh`, { method: 'POST', body: {} });
      say(`状態を再構築しました: ノード ${r.graph_nodes}件 / 辺 ${r.graph_edges}件（原典の再取得はしていません）`);
      renderTab();
    }));
    panel.append(button('参照の整合性を確認', async () => {
      const r = await wsFetch(`${base}/revalidate_references`, { method: 'POST', body: {} });
      say(`参照を確認しました: 成果物 ${r.artefacts_checked}件 / 壊れた参照 ${r.broken.length}件（原典の再取得はしていません）`);
    }));

    const arts = await wsFetch(`${base}/artefacts`);
    panel.appendChild(el('h3', '研究成果物（信頼状態つき）'));
    (arts.artefacts || []).forEach(a => {
      panel.appendChild(el('p', `${a.kind} / 信頼: ${a.trust} / ${a.title || ''}`));
    });

    const claimsData = await wsFetch(`${base}/claims`);
    panel.appendChild(el('h3', '主張と根拠評価'));
    (claimsData.claims || []).forEach(a => {
      const claim = (a.payload && a.payload.claim) || {};
      const assessments = (a.payload && a.payload.assessments) || [];
      const row = el('div');
      row.appendChild(el('p', `主張: ${claim.original_statement || a.title || ''}（評価 ${assessments.length}件 / 信頼: ${a.trust}）`));
      assessments.forEach(x => row.appendChild(el('p', `評価: ${x.status}（引用 ${x.citation_id || 'なし'}）`)));
      const citInput = document.createElement('input');
      citInput.type = 'text'; citInput.placeholder = '引用ID';
      row.append(citInput, button('引用を関連付け', async () => {
        if (!citInput.value.trim()) return;
        await wsFetch(`${base}/claims/${a.artefact_id}/citations`, { method: 'POST', body: { citation_id: citInput.value.trim() } });
        say('引用を関連付けました');
        renderTab();
      }), button('根拠を評価', async () => {
        const r = await wsFetch(`${base}/claims/${a.artefact_id}/assess`, { method: 'POST', body: {} });
        say(`根拠評価: ${(r.assessments || []).map(x => x.status).join(', ') || '根拠なし'}`);
        renderTab();
      }));
      panel.appendChild(row);
    });
  }

  async function renderDocuments() {
    const data = await wsFetch(`/api/workspace/documents?project_id=${encodeURIComponent(projectId)}`);
    const searchRow = el('div');
    const q = document.createElement('input');
    q.type = 'text'; q.placeholder = '保存資料・ノート・引用を検索';
    const resultsBox = el('div');
    q.addEventListener('change', async () => {
      const found = await wsFetch(`/api/workspace/search?project_id=${encodeURIComponent(projectId)}&q=${encodeURIComponent(q.value)}`);
      resultsBox.innerHTML = '';
      resultsBox.appendChild(el('p', `資料 ${found.documents.length}件 / ノート ${found.notes.length}件 / 引用 ${found.citations.length}件`));
    });
    searchRow.append(q, resultsBox);
    panel.appendChild(searchRow);
    const colls = await wsFetch(`/api/workspace/collections?project_id=${encodeURIComponent(projectId)}`);
    const collRow = el('div');
    const collName = document.createElement('input');
    collName.type = 'text'; collName.placeholder = '新規コレクション名';
    collRow.append(collName, button('コレクション作成', async () => {
      if (!collName.value.trim()) return;
      await wsFetch('/api/workspace/collections', { method: 'POST', body: { project_id: projectId, name: collName.value.trim() } });
      renderTab();
    }));
    for (const c of colls.collections) {
      collRow.appendChild(el('span', ` [${c.name}: ${c.document_count}件] `, 'meta-line'));
      collRow.appendChild(button(`「${c.name}」を削除`, async () => {
        if (!confirm(`コレクション「${c.name}」を削除しますか？（資料自体は削除されません）`)) return;
        await wsFetch(`/api/workspace/collections/${c.collection_id}`, { method: 'DELETE' });
        renderTab();
      }));
    }
    panel.appendChild(collRow);
    for (const doc of data.documents) {
      const card = el('article', undefined, 'card');
      card.appendChild(el('h3', doc.title || doc.record_id));
      card.appendChild(el('p', `${doc.author || ''} ${doc.publication_date || ''} · ${doc.library_id}:${doc.record_id}`, 'meta-line'));
      card.appendChild(el('p', `権利: ${(doc.rights_snapshot || {}).statement || 'unknown'}`, 'rights'));
      if (doc.rights_current) {
        card.appendChild(el('p', `最新の権利観測: ${doc.rights_current.latest_statement || ''}（区分: ${doc.rights_current.latest_category}、現在の抜粋保存: ${doc.rights_current.excerpt_storage_now ? '可' : '不可'}）`, 'rights'));
      }
      card.appendChild(el('p', `タグ: ${(doc.tags || []).join(', ') || 'なし'}`, 'meta-line'));
      const check = document.createElement('input');
      check.type = 'checkbox'; check.checked = compareSelection.has(doc.saved_document_id);
      check.addEventListener('change', () => {
        if (check.checked) compareSelection.add(doc.saved_document_id);
        else compareSelection.delete(doc.saved_document_id);
      });
      const checkLabel = el('label', ' 比較対象 ');
      checkLabel.prepend(check);
      card.appendChild(checkLabel);
      card.appendChild(button('タグ編集', async () => {
        const value = prompt('タグ（カンマ区切り）', (doc.tags || []).join(', '));
        if (value === null) return;
        await wsFetch(`/api/workspace/documents/${doc.saved_document_id}/tags`, { method: 'PUT', body: { tags: value.split(',').map(s => s.trim()).filter(Boolean) } });
        renderTab();
      }));
      if (colls.collections.length) {
        const sel = document.createElement('select');
        for (const c of colls.collections) {
          const opt = document.createElement('option');
          opt.value = c.collection_id; opt.textContent = c.name;
          sel.appendChild(opt);
        }
        card.appendChild(sel);
        card.appendChild(button('コレクションへ追加', async () => {
          await wsFetch(`/api/workspace/collections/${sel.value}/documents`, { method: 'POST', body: { saved_document_id: doc.saved_document_id } });
          say('コレクションに追加しました');
        }));
      }
      card.appendChild(button('削除', async () => {
        try {
          if (await deleteWithPreview(`/api/workspace/documents/${doc.saved_document_id}`, 'この資料を削除しますか？')) renderTab();
        } catch (e) { say(e.message); }
      }));
      panel.appendChild(card);
    }
  }

  async function renderCitations() {
    const data = await wsFetch(`/api/workspace/citations?project_id=${encodeURIComponent(projectId)}`);
    for (const cit of data.citations) {
      const card = el('article', undefined, 'card');
      card.appendChild(el('h3', cit.citation_key));
      card.appendChild(el('p', `ページ: ${cit.page_id} · 状態: ${cit.quotation_verification_status || 'not_checked'} · ページ対応: ${cit.page_mapping_status || 'unknown'} · 出所: ${cit.provenance} · 本文: ${cit.excerpt_stored ? '保存あり' : '参照のみ（本文なし）'}`, 'meta-line'));
      if (cit.original_excerpt) card.appendChild(el('blockquote', cit.original_excerpt, 'correction-quote'));
      else card.appendChild(el('p', `原文抜粋は保存されていません（${cit.excerpt_omitted_reason || '権利ポリシー'}）`, 'rights'));
      card.appendChild(button('再検証', async () => {
        const obs = await wsFetch(`/api/workspace/citations/${cit.citation_id}/reverify`, { method: 'POST', body: {} });
        say(`再検証: ${obs.status}`);
        renderTab();
      }));
      card.appendChild(button('削除', async () => {
        try {
          if (await deleteWithPreview(`/api/workspace/citations/${cit.citation_id}`, 'この引用を削除しますか？')) renderTab();
        } catch (e) { say(e.message); }
      }));
      panel.appendChild(card);
    }
  }

  async function renderNotes() {
    const docsData = await wsFetch(`/api/workspace/documents?project_id=${encodeURIComponent(projectId)}`);
    const form = el('div');
    const title = document.createElement('input');
    title.type = 'text'; title.placeholder = 'ノートの題';
    const content = document.createElement('textarea');
    content.rows = 4; content.placeholder = '研究ノート（あなた自身の考察）';
    const docSel = document.createElement('select');
    const none = document.createElement('option');
    none.value = ''; none.textContent = '関連付ける資料（任意）';
    docSel.appendChild(none);
    for (const d of docsData.documents) {
      const opt = document.createElement('option');
      opt.value = d.saved_document_id; opt.textContent = d.title || d.record_id;
      docSel.appendChild(opt);
    }
    let editingId = null;
    const saveBtn = button('ノートを保存', async () => {
      const body = { project_id: projectId, title: title.value, content: content.value,
                     saved_document_id: docSel.value || null };
      if (editingId) await wsFetch(`/api/workspace/notes/${editingId}`, { method: 'PUT', body });
      else await wsFetch('/api/workspace/notes', { method: 'POST', body });
      renderTab();
    });
    form.append(title, content, docSel, saveBtn);
    panel.appendChild(form);
    const data = await wsFetch(`/api/workspace/notes?project_id=${encodeURIComponent(projectId)}`);
    for (const note of data.notes) {
      const card = el('article', undefined, 'card');
      card.appendChild(el('h3', note.title || '（無題）'));
      card.appendChild(el('p', note.content));
      card.appendChild(el('p', `更新: ${note.updated_at}${note.saved_document_id ? ' · 資料にリンク' : ''}`, 'meta-line'));
      card.appendChild(button('編集', () => {
        title.value = note.title || '';
        content.value = note.content || '';
        docSel.value = note.saved_document_id || '';
        editingId = note.note_id;
        saveBtn.textContent = 'ノートを更新';
        title.focus();
      }));
      card.appendChild(button('削除', async () => {
        await wsFetch(`/api/workspace/notes/${note.note_id}`, { method: 'DELETE' });
        renderTab();
      }));
      panel.appendChild(card);
    }
  }

  async function renderComparisons() {
    panel.appendChild(el('p', `比較対象に選んだ資料: ${compareSelection.size}件（保存資料タブで選択、2〜4件）`));
    panel.appendChild(button('比較を実行して保存', async () => {
      if (compareSelection.size < 2) { say('2件以上選択してください'); return; }
      try {
        await wsFetch('/api/workspace/comparisons', { method: 'POST', body: { project_id: projectId, saved_document_ids: [...compareSelection] } });
        say('比較結果を保存しました');
        renderTab();
      } catch (e) { say(e.message); }
    }));
    const data = await wsFetch(`/api/workspace/comparisons?project_id=${encodeURIComponent(projectId)}`);
    for (const comp of data.comparisons) {
      const card = el('article', undefined, 'card');
      card.appendChild(el('h3', comp.title || '比較'));
      card.appendChild(el('p', `資料 ${ (comp.saved_document_ids || []).length }件 · 意味比較: ${comp.semantic_status}（未実施）`, 'meta-line'));
      const concepts = comp.dictionary_concept_overlap || {};
      const flat = [...new Set(Object.values(concepts).flat())];
      if (flat.length) card.appendChild(el('p', `共通概念候補: ${flat.slice(0, 20).join(', ')}`));
      for (const [docId, value] of Object.entries(comp.original_excerpts || {})) {
        if (Array.isArray(value)) {
          for (const entry of value.slice(0, 3)) {
            const text = typeof entry === 'object' ? entry.text : entry;
            if (text) card.appendChild(el('blockquote', text, 'correction-quote'));
          }
        } else if (value && value.omitted) {
          card.appendChild(el('p', `抜粋省略: ${value.omitted}`, 'rights'));
        }
      }
      for (const gap of comp.insufficient_evidence || []) {
        card.appendChild(el('p', `情報不足: ${gap.library_id || ''}:${gap.record_id || ''} — ${gap.reason || ''}`, 'rights'));
      }
      panel.appendChild(card);
    }
  }

  async function renderHistory() {
    const data = await wsFetch(`/api/workspace/history?project_id=${encodeURIComponent(projectId)}`);
    for (const h of data.history) {
      const card = el('article', undefined, 'card');
      card.appendChild(el('h3', h.original_query));
      card.appendChild(el('p', `${h.created_at} · ${(h.search_parameters || {}).mode || ''} · ${h.search_status} · 出所: ${h.provenance || 'server_recorded'}`, 'meta-line'));
      card.appendChild(button('再実行', () => {
        const params = h.search_parameters || {};
        document.getElementById('query').value = h.original_query;
        const mode = document.getElementById('mode-select');
        if (mode && params.mode) mode.value = params.mode;
        document.getElementById('materials-button')?.click();
      }));
      card.appendChild(button('削除', async () => {
        await wsFetch(`/api/workspace/history/${h.search_id}`, { method: 'DELETE' });
        renderTab();
      }));
      panel.appendChild(card);
    }
  }

  // ---- citation creation ------------------------------------------------
  let citeState = { library: '', pageId: '', token: '' };
  function openCite(library, pageId, token) {
    citeState = { library, pageId, token };
    currentTab = 'cite';
    renderTab();
  }
  async function renderCiteForm() {
    const lib = document.createElement('input');
    lib.type = 'text'; lib.placeholder = 'library_id'; lib.value = citeState.library;
    const page = document.createElement('input');
    page.type = 'text'; page.placeholder = 'page_id'; page.value = citeState.pageId;
    const text = document.createElement('textarea');
    text.rows = 10; text.readOnly = true;
    const info = el('p', 'ページを取得し、引用したい範囲をテキストエリアで選択してください。', 'meta-line');
    panel.append(lib, page, button('ページを取得', async () => {
      const res = await fetch(`/api/page?library=${encodeURIComponent(lib.value)}&id=${encodeURIComponent(page.value)}`);
      const data = await res.json();
      citeState = { library: lib.value, pageId: page.value, token: data.save_token || '' };
      text.value = data.contents || data.ocr_text || '';
      info.textContent = `ページ対応: ${data.ocr_state?.page_identity_verified ? '検証済み' : '未検証'} / 文字数: ${text.value.length}`;
    }), info, text, button('選択範囲を引用として保存', async () => {
      const excerpt = text.value.slice(text.selectionStart, text.selectionEnd);
      if (!excerpt) { say('範囲を選択してください'); return; }
      if (!citeState.token) { say('先にページを取得してください'); return; }
      try {
        let saved;
        try {
          saved = await wsFetch('/api/workspace/citations', { method: 'POST', body: { project_id: projectId, save_token: citeState.token, excerpt } });
        } catch (e) {
          // b8: NonCommercial licences need an explicit purpose
          // confirmation per save; ask and retry once with it.
          if (e.status !== 409 || !String(e.message).includes('nc_confirmation_required')) throw e;
          if (!confirm('この資料は非商用（NonCommercial）ライセンスです。非商用の研究目的での引用保存であることを確認しますか？')) { say('引用保存を中止しました'); return; }
          saved = await wsFetch('/api/workspace/citations', { method: 'POST', body: { project_id: projectId, save_token: citeState.token, excerpt, nc_purpose_confirmed: true } });
        }
        say(`引用を保存しました: ${saved.citation_key}（${saved.quotation_verification_status}）`);
      } catch (e) { say(e.message); }
    }));
  }

  // ---- export / import / backup ------------------------------------------
  async function download(path, filename) {
    const res = await fetch(path, { headers: {} });
    if (!res.ok) { say(`ダウンロード失敗: HTTP ${res.status}`); return; }
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  }
  function renderExport() {
    const pid = encodeURIComponent(projectId);
    const row = el('div');
    for (const [fmt, label] of [['bibtex', 'BibTeX'], ['ris', 'RIS'], ['csl-json', 'CSL JSON'], ['text', 'テキスト']]) {
      row.appendChild(button(`${label}をダウンロード`, () => download(`/api/workspace/export/documents?project_id=${pid}&format=${fmt}`, `documents.${fmt === 'csl-json' ? 'json' : fmt === 'bibtex' ? 'bib' : fmt === 'ris' ? 'ris' : 'txt'}`)));
    }
    row.appendChild(button('Markdownレポート', () => download(`/api/workspace/export/project?project_id=${pid}&format=markdown`, 'project.md')));
    row.appendChild(button('JSONエクスポート', () => download(`/api/workspace/export/project?project_id=${pid}&format=json`, 'project.json')));
    panel.appendChild(row);
    const file = document.createElement('input');
    file.type = 'file'; file.accept = 'application/json';
    panel.appendChild(file);
    panel.appendChild(button('JSONインポート（新規プロジェクトとして）', async () => {
      const f = file.files[0];
      if (!f) return;
      try {
        const payload = JSON.parse(await f.text());
        const result = await wsFetch('/api/workspace/import', { method: 'POST', body: payload });
        projectId = result.project.project_id;
        say('インポートしました（検証状態は申告情報として保持され、現在の検証済みにはなりません）');
        await loadProjects();
      } catch (e) { say(`インポート失敗: ${e.message}`); }
    }));
    panel.appendChild(button('バックアップ作成', async () => {
      const info = await wsFetch('/api/workspace/backup', { method: 'POST', body: {} });
      say(`バックアップを作成しました: ${info.id} (${info.bytes} bytes, sha256 ${String(info.sha256).slice(0, 12)}…)`);
      renderTab();
    }));
    const backupBox = el('div');
    panel.appendChild(backupBox);
    (async () => {
      const data = await wsFetch('/api/workspace/backup');
      for (const b of data.backups) {
        const line = el('div');
        line.appendChild(el('span', `${b.created_at} · ${b.bytes} bytes · `, 'meta-line'));
        line.appendChild(button('ダウンロード', () => download(`/api/workspace/backup/download?id=${encodeURIComponent(b.id)}`, 'workspace-backup.db')));
        line.appendChild(button('削除', async () => {
          await wsFetch(`/api/workspace/backup/${b.id}`, { method: 'DELETE' });
          renderTab();
        }));
        backupBox.appendChild(line);
      }
    })().catch(() => {});
    const restoreFile = document.createElement('input');
    restoreFile.type = 'file';
    panel.appendChild(restoreFile);
    panel.appendChild(button('バックアップから復元', async () => {
      const f = restoreFile.files[0];
      if (!f || !confirm('現在のDBは復元前に自動バックアップされます。復元しますか？')) return;
      const buf = await f.arrayBuffer();
      const result = await wsFetch('/api/workspace/restore?confirm=1', { method: 'POST', body: buf, headers: { 'Content-Type': 'application/octet-stream' } });
      say(`復元しました（復元前バックアップ: ${result.pre_restore_backup}）`);
      await loadProjects();
    }));
    panel.appendChild(button('プロジェクト名・説明を編集', async () => {
      const current = await wsFetch(`/api/workspace/projects/${projectId}`);
      const title = prompt('プロジェクト名', current.title);
      if (title === null) return;
      const description = prompt('説明', current.description || '');
      if (description === null) return;
      await wsFetch(`/api/workspace/projects/${projectId}`, { method: 'PUT', body: { title, description } });
      await loadProjects();
    }));
    panel.appendChild(button('アーカイブ / 解除', async () => {
      const current = await wsFetch(`/api/workspace/projects/${projectId}`);
      await wsFetch(`/api/workspace/projects/${projectId}`, { method: 'PUT', body: { archived: !current.archived_at } });
      say(current.archived_at ? 'アーカイブを解除しました' : 'アーカイブしました');
      await loadProjects();
    }));
    panel.appendChild(button('プロジェクトを削除', async () => {
      try {
        await wsFetch(`/api/workspace/projects/${projectId}`, { method: 'DELETE' });
      } catch (e) {
        if (!confirm(`${e.message}\n本当に削除しますか？（バックアップやエクスポート済みファイルには残る場合があります）`)) return;
        await wsFetch(`/api/workspace/projects/${projectId}?confirm=1`, { method: 'DELETE' });
        projectId = '';
        await loadProjects();
      }
    }));
  }

  // ---- history recording (called from app.js) ------------------------------
  window.glmWorkspace = {
    recordHistory(data, q, mode, searchStatus) {
      const toggle = document.getElementById('ws-save-history');
      if (!toggle?.checked || !projectId) return;
      // Preferred path: the server vouches for what it ran via
      // a history token bound to its own response snapshot.
      if (data.history_token) {
        wsFetch('/api/workspace/history', {
          method: 'POST',
          body: { project_id: projectId, history_token: data.history_token },
        }).catch(() => {});
        return;
      }
      // Fallback (older responses): a manual entry, which the
      // server stores marked as user-entered, never as proof.
      wsFetch('/api/workspace/history', {
        method: 'POST',
        body: {
          project_id: projectId,
          original_query: q,
          search_parameters: { mode, kind: 'materials' },
          result_summary: { materials: (data.materials || []).length },
          search_status: searchStatus,
        },
      }).catch(() => {});
    },
  };

  loadProjects().catch(e => say(e.message));
})();
