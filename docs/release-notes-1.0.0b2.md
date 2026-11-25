# Release notes — Global Library MCP 1.0.0b2 (draft / 案)

## 日本語

**Global Library MCP 1.0.0b2 — Research Beta**

世界の図書館を横断して研究資料を探し、原典のページOCRと原本画像で
裏付けを確認するための基盤です。本バージョンは Research Beta で、
有料LLMなしで動作します。

### できること

- 図書館横断検索（書誌検索）
- 国立国会図書館（NDL）と Internet Archive のページ単位OCR取得
- IIIF等による原本ページ画像へのアクセスと原本確認
- 研究資料モード（候補資料・抜粋・引用情報を、根拠と区別して提示）
- 文献比較
- MCPサーバーとしての接続（MCPクライアントからツール利用可能）
- Web UI（日本語／英語）

### 1.0.0b2 の変更点

- Internet Archive のOCR取得元の正確性向上：実際に取得したファイル名・
  形式・URLを出典として返すようになりました（従来は推測したファイル名を
  表示していました）。
- 複数巻資料の扱いを明示：ページと原本画像の対応が確認できない複数巻
  アイテムでは「未検証」と表示し、検証済み証拠として扱いません。
- 単一ファイルの場合の「検証済み」も、メタデータ上でOCRの葉順と原本
  画像の並びが整合するという意味であり、画像そのものとの完全な照合を
  保証するものではありません。学術利用では原本画像での確認を推奨します。

### AI回答について

AI回答機能は **実験段階（AI Experimental）** です。Research Beta の
標準では無効で、資料検索・OCR・原本閲覧はAIなしで利用できます。

### 対応図書館と既知の制約

- NDL：実地検証済み（次世代デジタルライブラリー／NDLサーチ）。
- Internet Archive：実地検証済み。貸出限定資料は取得しません。
  複数巻アイテムは現状、第1ファイルのOCRのみ・対応未検証表示。
- Gallica/BnF：アダプター実装済みですが、開発ネットワークから上流が
  403を返すため未検証です。
- Europeana 等の一部機関は利用上限が未確認です。各機関の利用条件は
  `docs/phase10-library-terms.md` を参照してください。
- 検索予算はサービス層のユニット単位で数えます（リトライ等を含む
  実HTTPリクエスト数そのものではありません）。
- キャッシュは容量上限あり・TTLなし。

### ローカルインストール

```sh
git clone https://github.com/shellingford570/global-library-mcp
cd global-library-mcp
git checkout v1.0.0b2
python3 -m venv .venv && .venv/bin/pip install .
.venv/bin/global-library-mcp web --port 8000   # Web UI
.venv/bin/global-library-mcp mcp              # MCPサーバー (stdio)
```

Docker でも起動できます（`docker build -t global-library-mcp .`）。
APIキーは不要です。

---

## English

**Global Library MCP 1.0.0b2 — Research Beta**

A research infrastructure for discovering library materials across
libraries worldwide, reading page-level OCR, and checking claims
against original page images. This Research Beta works with **no
paid LLM**.

### What it does

- Cross-library bibliographic search
- Page-level OCR from the National Diet Library (NDL) and the
  Internet Archive
- Access to original page images (IIIF etc.) and original-page
  verification
- Research-materials mode (candidate materials, excerpts and
  citations, clearly separated from verified evidence)
- Document comparison
- MCP server (tools usable from MCP clients)
- Web UI in Japanese and English

### Changes in 1.0.0b2

- More accurate Internet Archive OCR provenance: the source now
  reports the file actually fetched (name, format, URL) instead
  of a guessed file name.
- Explicit multi-volume handling: when the correspondence between
  OCR pages and page images cannot be confirmed, pages are shown
  as **unverified** and never treated as verified evidence.
- Even a "verified" mapping for single-file items means the OCR
  leaf order is consistent with the item's page-image sequence
  as far as the metadata shows; it is not a pixel-level collation
  against the original image. Check quotations against the
  original page image before scholarly use.

### About AI answers

AI answering is **experimental (AI Experimental)** and disabled by
default in the Research Beta. Materials search, OCR and
original-page viewing work without any AI.

### Supported libraries and known limitations

- NDL: live-verified.
- Internet Archive: live-verified. Lending-restricted items are
  never fetched. Multi-volume items currently expose the first
  file's OCR, labelled unverified.
- Gallica/BnF: adapter implemented; the upstream returns 403 from
  the development network, so it is not live-verified.
- Some libraries (e.g. Europeana) have unverified usage limits.
  See `docs/phase10-library-terms.md` for per-library terms.
- The request budget counts service-level units, not raw HTTP
  requests including retries.
- Caches are size-capped with no TTL.

### Local install

```sh
git clone https://github.com/shellingford570/global-library-mcp
cd global-library-mcp
git checkout v1.0.0b2
python3 -m venv .venv && .venv/bin/pip install .
.venv/bin/global-library-mcp web --port 8000   # Web UI
.venv/bin/global-library-mcp mcp              # MCP server (stdio)
```

Docker works too (`docker build -t global-library-mcp .`).
No API key is required.
