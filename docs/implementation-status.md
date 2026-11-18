# v1.0 実装・検証状況

確認日: 2026-11-19

## 実装済み

Phase 0の成果物を基に、共通データモデル、図書館レジストリ、公式MCP Python SDKによるstdioサーバー、並列検索、重複排除、部分エラー、権利・出典保持、APIキー不要のWeb UIを実装した。LoC、NDL、Gallicaに加え、Internet Archive、DDB、Europeanaのアダプターも追加した。DDBとEuropeanaは資格情報・上流条件が必要なため、未設定時に成功扱いせず明示エラーを返す。

NDLについては、公式の次世代デジタルライブラリーAPIに合わせてBook/Page APIとIIIF Image APIを追加した。Book APIの検索結果からPIDを取得し、Page APIでコマ番号・OCR本文・座標JSONを取得し、座標JSONしか返らないページでは文字列を復元する。画像URLはNDL公式のIIIF URLから生成する。

AI検索はOpenAI互換プロバイダー交換層を実装した。LLMはデフォルト無効で、`LLM_ENABLED=true`を明示しない限り外部モデルへ通信しない。回答プロンプトは検索結果だけを根拠に使い、原文・翻訳・出典・権利・不足情報を分離する。

## ライブ検証結果

- **NDL**: 成功。`https://lab.ndl.go.jp/dl/api/book/search?keyword=発電&size=...` で9件を取得。PID `974405`についてBook API、Page API、OCR座標復元、IIIF画像URL `https://dl.ndl.go.jp/api/iiif/974405/R0000002/full/full/0/default.jpg` を検証した。ページ2の実レスポンスでは`contents`が空でも`coordjson`から「大正元年 發電水力事業緊覽 臨時發電水力調査局」を復元し、`verified_mapping=true`となった。
- **Internet Archive**: 成功。Advanced Search APIで`railway`を検索し、NDLとのライブ横断検索で結果が両機関から返ることを確認した。2機関横断は16件、エラー0件だった。
- **Library of Congress**: 未成功。公式APIはAPIキー不要だが、JSON/YAML APIは毎分20リクエスト、超過時はブロックされる。今回の実行環境からはCloudflare challengeを伴う403が返った。リトライで回避せず、部分エラーとして返す。
- **Gallica/BnF**: 未成功。BnF公式ポータルはSRU・IIIF・API Documentへの一時的アクセス制限を告知している。今回のSRUライブ呼び出しも403となった。アクセス制限中のため成功扱いにしない。
- **DDB**: 未検証。アダプターは追加したが、この環境での公式API資格条件を満たすライブ成功は確認していない。
- **Europeana**: 未検証。`EUROPEANA_API_KEY`なしではリクエストせず、資格情報が必要であることをエラーにする。
- **LLM**: モック応答で構造化回答の検証済み。実モデル呼び出しは費用・資格情報を伴うため、明示的な有効化なしでは実行していない。

公式条件の参照先は、[LoC JSON/YAML API](https://www.loc.gov/apis/json-and-yaml/)、[LoC Working Within Limits](https://www.loc.gov/apis/json-and-yaml/working-within-limits/)、[BnF Gallica APIポータル](https://api.bnf.fr/fr)、[BnFのGallicaアクセス制限告知](https://api.bnf.fr/fr/evolution-des-modalites-dacces-aux-api-de-gallica)、[NDL次世代デジタルライブラリーAPI](https://lab.ndl.go.jp/service/tsugidigi/apiinfo/) である。

## 検証コマンド

```bash
. .venv/bin/activate
pytest -q
curl -fsS http://127.0.0.1:8000/health
curl -fsS 'http://127.0.0.1:8000/api/search?q=railway&libraries=ndl,internet-archive'
curl -fsS 'http://127.0.0.1:8000/api/document?library=ndl&id=974405'
curl -fsS 'http://127.0.0.1:8000/api/page?library=ndl&id=974405_2'
```

Dockerfileとdocker-compose.ymlは追加済みだが、このサンドボックスにはDocker CLIが存在せず、実ビルド・コンテナ起動は未確認である。公開デプロイや有料契約は実施していない。
