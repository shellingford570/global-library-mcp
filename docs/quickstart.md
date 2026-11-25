# クイックスタート — Global Library MCP 1.0.0b2 (Research Beta)

世界の図書館を横断検索し、原典のページOCRと原本画像で裏付けを取るための
研究支援ツールです。有料LLM APIは不要です。AI回答機能は実験段階で、
初期設定では無効になっています。

English version: [quickstart.en.md](quickstart.en.md)

## 1. インストール

必要なもの：Python 3.11以上、Git。

```sh
git clone https://github.com/shellingford570/global-library-mcp
cd global-library-mcp
git checkout v1.0.0b2
python3 -m venv .venv
.venv/bin/pip install .
```

Windows（PowerShell）の場合：

```powershell
git clone https://github.com/shellingford570/global-library-mcp
cd global-library-mcp
git checkout v1.0.0b2
py -m venv .venv
.venv\Scripts\pip install .
```

Dockerの場合：

```sh
docker build -t global-library-mcp .
docker run --rm -p 8000:8000 global-library-mcp
```

## 2. Web UIの起動

```sh
.venv/bin/global-library-mcp web --port 8000
```

ブラウザで http://127.0.0.1:8000 を開きます（Windowsでは
`.venv\Scripts\global-library-mcp web --port 8000`）。

## 3. 最初の検索

画面上部の検索窓に、知りたいことを文章で入力します（例：
「明治時代の水力発電について書かれた資料」）。結果は3種類に分かれます。

- **証拠（verified）**：ページの同一性が確認でき、引用をそのまま
  使えるページ
- **関連資料**：関連するが未検証のページ
- **未検証（unverified）**：原本との対応が確認できなかったページ。
  資料そのものは有用でも、引用には原本画像での確認が必要です

## 4. OCRの読み方

各ページにはOCR本文が表示されます。OCRには誤認識が含まれます。
重要な引用は、必ず原本画像と見比べてください。「検証済み」は
「メタデータ上でページ対応が整合している」という意味で、
OCRの正確さそのものを保証するものではありません。

## 5. 原本画像の確認

各ページの「原本」リンクから、図書館が提供する原本ページ画像
（NDLはIIIF、Internet ArchiveはBookReader画像）を開けます。
引用前に、ページ番号と本文が一致しているか目視で確認してください。

## 6. 文献比較

「文献比較」では2つの資料を指定し、同じテーマについて両資料の
ページ抜粋を並べて確認できます。

## 7. 引用情報の取得

各証拠には引用キー（例：`ndl:992954:992954@12`）が付きます。
論文・レポートへの引用には、引用キーと原本URLを併記してください。

## 8. MCP接続

MCPクライアント（Claude Desktop、Claude Code、Cursor、
Google Antigravity など、stdio型MCP対応クライアント）からは
MCPサーバーとして使えます。設定例は
[mcp-clients.md](mcp-clients.md) を参照してください。

起動コマンドは `global-library-mcp mcp`（stdio）です。

## 9. エラー時の対応

- **特定の図書館だけエラー（403など）**：実行環境のネットワークから
  その図書館へ届いていない可能性があります。別のネットワークで
  試すか、他の図書館の結果を利用してください。実装の不具合とは
  限りません。
- **結果が0件**：検索語を短くするか、別言語（日本語／英語）で
  試してください。
- **複数巻資料が「未検証」になる**：仕様です。原本リンクから
  図書館のビューアで直接確認してください。

## 10. 対応図書館

- 対応済み（実地検証済み）：国立国会図書館（NDL）、Internet Archive
- 調査段階：Gallica/BnF、Europeana、Library of Congress、DDB ほか。
  対応済みと調査段階は別物です。各機関の利用条件は
  [phase10-library-terms.md](phase10-library-terms.md) を参照。

## 11. 利用条件

各資料の権利は所蔵機関と資料ごとに異なります。ページに表示される
権利情報を確認し、出典を明示して利用してください。貸出限定資料は
取得しません。

## 12. バグ報告方法

GitHub Issues から報告できます：
https://github.com/shellingford570/global-library-mcp/issues

テンプレートの分類（検索結果／OCR品質／原本対応／図書館接続／
MCP接続／UI／セキュリティ／新規図書館の追加要望）に沿って
記入してください。**個人情報・APIキー・機密資料は投稿しないで
ください。**
