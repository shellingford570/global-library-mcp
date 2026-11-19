# v1.0 リリース候補コードレビュー

確認日: 2026-11-19

## 判定

現時点は **v1.0正式リリース不可**。MCPの基本stdio起動、NDLのBook/Page/OCR/IIIFリンク、Internet Archive/DDBを含む横断検索、Python回帰テストは動作する。一方、公開配置前にセキュリティと証拠整合性の修正が必要である。

## 今回修正した項目

- upstream例外のURLクエリをサニタイズし、Europeanaの`wskey`をWeb/MCPのエラー応答へ漏えいさせないようにした。
- LLMの`LLM_API_BASE`をHTTPS・公開ホストに限定し、プライベートIP、loopback、`.local`、埋め込み資格情報を拒否するようにした。
- LLMが返す引用番号を、供給した証拠の範囲内に検証するようにした。
- NDLページの`id`、book PID、page番号、OCR本文の存在を突合して`verified_mapping`を計算するようにした。OCR由来（contents/coordjson）、取得時刻、原API URL、権利確認注意を返す。
- `get_citation`のページ／レコード判定を修正し、ページ根拠がある場合を`page-level`とした。`get_page_image`は0以下のページを拒否する。
- 横断検索で未知ライブラリを部分エラーとして明示し、重複IDを除去し、全体limitを適用した。タイトル・著者だけで別資料を誤統合しないよう、landing URLまたは機関＋record IDをキーにした。
- Internet Archive、DDB、Europeanaの検索を共通HTTP処理へ寄せ、レスポンス型・権利値・多値フィールドを安全に正規化した。
- Web UIの原本リンクをHTTPSに限定し、DDB/Europeanaを選択可能にした。AI無効時にも検索結果を表示し、状態通知、二重送信抑止、取得時刻の安全なフォールバックを追加した。
- Web APIに入力長制限、セキュリティヘッダー、秘密を含む内部例外の抑制を追加した。
- Dockerをnon-root、read-only、capability drop、no-new-privileges、healthcheck付きにした。CIにはDocker実バックエンドのAPIスモークとPlaywright失敗証跡アップロードを追加した。
- Python配布版数を`1.0.0rc1`へ統一した。

## 残るブロッカー

1. **ライブ外部APIの再検証**: この監査環境ではDocker CLIがなく、監査中にLoC/Gallica/DDB/Europeanaのライブ成功を再主張していない。LoC/Gallicaは過去に公式制限または403、EuropeanaはAPIキー必須として未成功扱いを維持する。DDBは資格情報なしの公開v2経路に公式資料間の説明差があるため、`DDB_API_KEY`有り・無しの両方をCI外の契約試験で確認する必要がある。
2. **権利・IIIFの完全な証拠モデル**: NDLの画像URLは公式形式を生成するが、manifest/Canvasの取得と画像応答の実在検証、印刷ページ番号、座標bboxの構造化は未実装。公開APIの`iiif=true`能力表示は、manifest証拠まで保証する意味には使わないこと。
3. **全アダプターの共通レート制御**: LoC以外のプロバイダー別クォータとRetry-After処理を、利用条件に基づいて設定する必要がある。現在は固定の一般化レート制御を成功扱いしない。
4. **依存再現性**: Pythonのlock/constraints、SBOM、脆弱性スキャンは未導入。正式公開前に追加する。
5. **認証・公開運用**: Web UI/APIは認証なしの開発用ゲートウェイであり、公開デプロイには認証、レート制限、上流クォータ保護、監視、TLS終端が必要。LLM実呼び出しはユーザーが承認済みの資格情報を安全なSecretとして設定した場合に限る。

## テスト結果

- `python -m compileall -q src tests`: 成功。
- `.venv/bin/pytest -q`: **15 passed**（既存9件＋監査回帰6件）。モック試験であり、これだけで外部APIのライブ成功は意味しない。
- `npm run test:e2e`: 既存のPlaywright Chromiumシナリオは過去に2件成功。今回の監査環境ではNode/ブラウザを再実行した証跡を別途作成していないため、最新成功とは扱わない。
- Docker build/run: 監査環境にDocker CLIがないため未実施。GitHub Actionsの過去run成功記録は実装状況文書に残るが、この監査から独立に再検証したものではない。

## 正式リリース前チェックリスト

- [ ] Docker/Composeのbuild、healthcheck、non-root実行、Playwright、`tests/e2e_smoke.sh`をGitHub Actionsで新コミット上で成功させる。
- [ ] NDLの実ページでレスポンスID/PID/page、OCR、IIIF URLを突合し、複数資料・分割ページの契約試験を追加する。
- [ ] LoC/Gallica/DDB/Europeanaを成功・未成功・資格情報待ちに分けて、実行日時とHTTP結果を記録する。
- [ ] 依存lock/脆弱性スキャン/SBOM、CHANGELOG、Contributing、公開脆弱性窓口を整える。
- [ ] 本番デプロイ、外部APIキー発行、LLM有料利用は事前承認後にのみ実施する。
