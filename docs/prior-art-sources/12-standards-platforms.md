# Phase 0調査メモ: MCP、IIIF、SRU、OAI-PMH、Dublin Core、MARC21、ALTO、METS、Unicode/BCP47と横断検索基盤

- **確認日**: 2026-11-19
- **対象**: 新規 Global Library MCP 実装前の事実確認
- **調査方針**: 公式仕様、公式API文書、標準団体・標準管理機関の原ページを優先。検索結果スニペットだけでは断定しない。確認できない事項は unknown とした。

## 1. Model Context Protocol（MCP）と公式 MCP Registry

### 公式に確認できた事実

Model Context Protocol は、LLMアプリケーションと外部データ・ツールを接続するためのオープンプロトコルである。公式仕様リポジトリには仕様、プロトコルスキーマ、公式ドキュメントが含まれ、TypeScriptを正本としてJSON Schemaも提供している。GitHubリポジトリはMIT Licenseで、2026-11-19確認時点でコミット数は5,015と表示された。[1]

公式MCP Registryは、公開MCPサーバーのメタデータを中央管理するサービスで、DNS検証を伴う名前空間管理、REST API、標準化されたインストール・設定情報を提供する。server.jsonには一意名、npm等のパッケージまたはリモートURL、実行コマンド・環境変数、サーバー能力などが含まれる。[2]

Registryは2026-11-19時点でpreviewであり、破壊的変更やデータリセットの可能性がある。公開サーバー向けで、private serverは対象外。Registryは実コードのセキュリティ監査を代行せず、npm/PyPI/Docker等の下位レジストリと下流aggregatorにスキャン・キュレーションを委ねる。したがって、登録済みであることはコードの安全性を意味しない。[2]

### API/能力の確認

MCPの仕様・スキーマは、ツール、リソース、プロンプト等のプロトコル機能を定義するが、図書館コンテンツそのものの全文検索、OCR、画像配信、ページ単位取得、IIIF/SRU/OAI-PMHを標準で提供するものではない。これらは個別MCPサーバーが下流APIを実装・ラップするかどうかに依存する。Global Library MCPについて、どのMCPツール名・入力スキーマ・返却形式を実装済みかは本調査資料だけでは確認できずunknown。

### ライセンス、保守、再利用、注意

仕様リポジトリのMIT Licenseは再利用しやすい。一方、Registryはpreviewであり、Namespace認証は出所の説明責任を高めるが、依存パッケージやリモートサーバーの脆弱性・プロンプトインジェクション・過剰権限を保証しない。導入時は固定バージョン、依存関係スキャン、通信先allowlist、最小権限、タイムアウト、監査ログ、応答サイズ上限を別途実装する必要がある。公式に確認できる最終更新日は、リポジトリ画面の個別コミット履歴を採用する運用が必要で、長期保守保証はunknown。

## 2. IIIF

### 公式に確認できた事実

IIIFは高品質で帰属可能なデジタルオブジェクトをオンライン提供するためのオープン仕様群で、国際的な文化機関のコンソーシアムに支えられている。[3] 2026-11-19確認時点のcurrent specificationsは、Image API 3.0、Presentation API 3.0、Authorization Flow API 2.0、Change Discovery API 1.0、Content Search API 2.0、Content State API 1.0。Presentation API 4.0はrelease candidateのdraftである。[3]

Image APIはHTTP(S) URIで画像の領域、サイズ、回転、品質、形式を指定して返す。Presentation APIは書籍等の複合デジタルオブジェクトをビューアで提示するためのモデルである。[3] したがって画像取得、画像の領域・サイズ指定、ページ／Canvas単位の取得、複合オブジェクトの順序・構造表現に再利用性が高い。

Content Search API 2.0は、単一のIIIF resource（Manifest、Canvas、Range、Collection等）に結びついたAnnotation内容を検索する仕組みで、OCR、転写、翻訳、字幕等を想定する。メタデータや一般的な記述プロパティの検索は仕様の範囲外。HTTP GETのq等で検索し、Annotation Page/Collectionとして結果を返す。サービスはManifest、Range、Canvas等のスコープに関連付けられる。[4]

### API可否

- 全文検索: **可**（Content Search API。ただし提供者がannotation/OCRを公開し、SearchServiceを実装している場合）。
- OCR: **可／保持形式は実装依存**。IIIF SearchはOCR由来テキストを検索できるが、OCR生成自体はIIIF仕様の責務ではない。
- 画像: **可**（Image API）。
- ページ単位取得: **可**（Presentation APIのCanvas、Image APIの領域・サイズURI。具体的URIは機関実装依存）。
- IIIF/SRU/OAI-PMH: **IIIFは可**。SRU/OAI-PMHはIIIFの仕様ではなく、個別機関の併用状況は別確認が必要。横断的に常に使えるとは断定不可。

### 保守・ライセンス・注意

公式サイトにはcurrentとdraft、旧版、validator、Editorial Processが掲載され、更新・保守活動が継続している。旧版の実装・参照実装は新major versionをまたいで維持される保証がない。[3] 仕様本文のライセンス条件はこのトップページだけでは明示確認できず、個別リポジトリ・仕様ファイルのライセンス確認が必要（unknown）。URIが外部画像・Annotationを参照するため、認証、CORS、可用性、アクセス制御、著作権は機関ごとに確認する。

## 3. SRU / CQL

### 公式に確認できた事実

SRU（Search/Retrieve via URL）は、CQL（Contextual Query Language）を用いるXMLベースの検索プロトコルである。Library of Congressの公式ページはSRU 1.1、1.2、SRU 2.0、CQL、Explain、Scan、record schema等を掲載している。1.1は2004年、1.2は2007年、SRU 2.0はOASIS Standardと記載されている。[5]

### API可否

- 全文検索: **プロトコルとして可**（インデックスとrecord schemaをサーバーが提供する場合）。全文を必須とはしない。
- OCR: **unknown／サーバー依存**。SRU自体はOCR生成・保存を規定しない。
- 画像: **unknown／サーバー依存**。検索結果に画像リンクを含める機関はあり得るがSRU標準機能ではない。
- ページ単位取得: **unknown／サーバー依存**。通常は検索レコードの取得であり、デジタルページ画像の配信仕様ではない。
- IIIF/OAI-PMH: **SRU仕様外**。機関が併用するかは個別確認が必要。

### 保守・再利用・注意

LC公式ページのフッターは2016-07-29で、ページ上の仕様更新日と現在の実装稼働状況は一致しない可能性がある。SRU 2.0のOASIS標準化は確認できるが、各機関の実装バージョン、レコードスキーマ、認証、レート制限、可用性はunknown。CQLのフィールド名・コンテキストセットは相手サーバーのExplainを必ず参照し、検索語を機械的に共通化しない。

## 4. OAI-PMH

### 公式に確認できた事実

OAI-PMH 2.0は2002-06-14のプロトコル仕様で、公式ページの文書版は2015-01-08。メタデータharvestingのアプリケーション非依存相互運用フレームワークであり、Data Provider（メタデータを公開するrepository）とService Provider（harvestして価値付加サービスを構築）を区別する。[6]

HTTPリクエストとXML応答を用い、GetRecord、Identify、ListIdentifiers、ListMetadataFormats、ListRecords、ListSetsの6 verbを規定する。metadataPrefix、from/until、set、resumptionTokenによる選択的harvest・ページング・再開が可能。Dublin Core（oai_dc）は標準的なmetadata formatの一つだが、リポジトリごとに追加形式を公開できる。[6]

### API可否

- 全文検索: **不可（検索プロトコルではない）**。リポジトリ全体のメタデータ収集用。収集後の全文検索は別基盤。
- OCR: **unknown／metadata formatまたはデータプロバイダ依存**。OCR本文を返すことは仕様上必須でない。
- 画像: **unknown／レコード中の外部リンク等に依存**。画像配信はOAI-PMHの責務ではない。
- ページ単位取得: **不可と断定するより、仕様上の対象外**。GetRecordはアイテムのmetadata recordを取得するが、デジタルページ画像の取得APIではない。
- IIIF/SRU: **仕様外**。同一機関が併用する場合は個別接続。

### 保守・ライセンス・注意

OAI-PMH 2.0は2002年以降安定し、公式仕様の文書版が2015年である。保守団体・仕様は存在するが、頻繁な更新を前提とする標準ではない。harvest時はresumptionToken、削除レコード、UTC日時、set、metadataPrefix、再実行の冪等性を扱う必要がある。大量取得では相手の利用規約と負荷制限を順守する。ライセンス条項は当該仕様ページ本文から明示的に確認できずunknown。

## 5. Dublin Core / DCMI Metadata Terms

### 公式に確認できた事実

DCMI Metadata TermsはDCMIが維持する全metadata terms（properties、vocabulary encoding schemes、syntax encoding schemes、classes）の最新仕様である。公式ページのIdentifierは2020-01-20版、Document StatusはDCMI Recommendation。15要素に限定されず、terms namespaceに多数のプロパティ・クラスを含む。[7]

公式サイト検索結果およびページの文書案内では、DCMI文書はCreative Commons Attribution 4.0 International License（CC BY 4.0）でライセンスされると記載されている。[8]

### API可否

Dublin Coreはメタデータ語彙でありAPIではない。全文検索、OCR、画像、ページ単位取得、IIIF/SRU/OAI-PMHを自ら提供しない。OAI-PMHのmetadataPrefixや横断検索基盤の正規化フィールドとして再利用できるが、値の品質、言語、識別子、権利情報は提供者依存。

### 保守・注意

最新の公開仕様が2020-01-20版であることは確認できるが、語彙の変更履歴、現在のUsage Board活動、実装ライブラリの脆弱性は別途確認が必要。DCMI termsの語彙を検索スキーマに使う場合、dc:title等15要素だけに固定せずdcterms:subject、identifier、language、rights、license等を保持する。Dublin Coreの存在はフルテキストや画像の存在を意味しない。

## 6. MARC21

### 公式に確認できた事実

Library of Congressの公式MARCページは、Bibliographic、Authority、Holdings、Classification、Communityの5形式とMARC Lite、コードリスト、record structure、character sets、exchange mediaを掲載する。MARC formatsは、機械可読な書誌その他関連情報の表現・通信の標準で、コミュニティ主導でLCがcoordinatorと説明されている。[9]

### API可否

MARC21はデータ形式でありAPIではない。全文検索、OCR、画像、ページ単位取得、IIIF/SRU/OAI-PMHを自ら提供しない。SRUのrecord schema、OAI-PMHのmetadata format、MARCXML変換、機関内検索インデックスの入力として利用できる。書誌・典拠・所蔵・分類を統合するにはMARCのrecord typeとフィールド定義を保持する必要がある。

### 保守・ライセンス・注意

LCページには2026-09-24のページ日付と、次回MARC Advisory Committee meeting 2027-01-27/28が掲載され、保守活動は継続していると判断できる。[9] MARC仕様本文の再利用ライセンスはページから明示確認できずunknown。固定長leader、directory、subfield、文字コード、MARC21とMARCXMLの差を正しく処理し、未定義フィールド・ローカルフィールド・誤った文字コード変換でデータを失わないことが必要。

## 7. ALTO

### 公式に確認できた事実

ALTO（Analyzed Layout and Text Object）は、書籍・新聞等の物理テキスト資源のレイアウトと内容を記述するXML Schemaで、METSのadministrative metadataの拡張として使われることが多いが、単独文書でも使える。[10]

LC公式ページのニュース欄はSchema Version 4.4 releasedを2023-04-07として掲載し、current version欄は4.3と表示する一方、Version 4.4 official XSDリンクも掲載している。この表示の不整合は公式ページ内で確認できるため、採用時はXSD実体とnamespaceを検証する必要がある。[10] Version 4.4ではPageTypeのLANG、ROTATION、OTHERLANGS等が追加された。ALTO 4.0で標準ライセンスをCC BY-SA 4.0に明確化したとの変更履歴がある。[10]

### API可否

ALTOはAPIではない。全文検索はALTOのString/Glyph等のテキストを取り込めば実装できるが、ALTO単体に検索エンドポイントはない。OCR本文・文字位置・ページ／ブロック／行レイアウト表現には適する。画像、ページ単位取得、IIIF/SRU/OAI-PMHはALTOの仕様外で、METS、IIIF、機関API等との組み合わせが必要。

### 保守・セキュリティ

LCがALTO version 2.0以降の公式maintenance agencyと記載され、GitHubのaltoxmlコミュニティも案内されている。[10] XML処理時はXXE、外部エンティティ、巨大入力、XPathインジェクションを防ぎ、XSD検証の前に安全なXMLパーサ設定を行う。ライセンスは4.0以降CC BY-SA 4.0の確認があるが、各schema・文書・付属サンプルの扱いは個別確認する。

## 8. METS

### 公式に確認できた事実

METS（Metadata Encoding and Transmission Standard）はデジタルライブラリ内オブジェクトのdescriptive、administrative、structural metadataをXML Schemaで符号化する標準。DLFのイニシアティブとして始まり、METS BoardがLCのNetwork Development and MARC Standards Officeと協力して維持する。[11]

LC公式サイトにはMETS 1 schema/documentation、METS 2 schema/documentation、外部schema、example、profile、implementation registry、GitHub、Editorial Boardを掲載。METS 2 initial versionは2025-03-03にリリースされたと表示され、2026-08-11のiPRES 2026 workshop案内もある。[11]

### API可否

METSはAPIではない。全文検索、OCR、画像、ページ単位取得、IIIF/SRU/OAI-PMHを自ら提供しない。structMapでページ・ファイルの関係を表し、ALTO、MIX、rights schema等と組み合わせてデジタルオブジェクトのパッケージを表現できる。実際のバイナリ、画像配信、ページ取得はfileSecの参照先やIIIF等の外部サービスに依存する。

### 保守・再利用・注意

METS 1とMETS 2が併存するため、実装対象バージョン、namespace、profile、既存機関の適合範囲を必ず固定する。XML処理上のXXE等の注意はALTOと同様。METSのschema・文書・サンプル全体のライセンスは公式トップページで明示確認できずunknown。再利用に際してはGitHub各リポジトリのLICENSEを個別確認する。

## 9. Unicode / BCP 47

### 公式に確認できた事実

Unicode Standardの正式な版は、core specification、Code Charts、Unicode Standard Annexes、Unicode Character Databaseの組合せで定義される。公式の機械可読データは無料ダウンロードでき、Unicode Technical Committeeが継続保守する。安定性ポリシー、errata、版別アーカイブが公開されている。[12]

BCP 47はRFC 5646（Tags for Identifying Languages）とRFC 4647で構成される。RFC 5646は言語タグの構造・内容・構築・意味を定義し、言語タグはハイフン区切りの英数字subtag列。IANA Language Subtag Registryが有効なsubtagのデータ源であり、RFC 5646単独ではなくRFC 4647と併せて言語タグの識別・matchingに使う。[13]

### API可否

Unicode/BCP47は検索・OCR・画像・ページ取得APIではない。Unicodeは文字コード・正規化・文字特性・スクリプト等の基盤、BCP47はメタデータの言語識別とlocale negotiationの基盤である。Global Library MCPでは、Unicode正規化方針、検索のcase/diacritic/folding、BCP47タグ（例: ja、en、zh-Hant、pt-BR）を明示し、MARC/Dublin Core/ALTO/IIIFのlanguage値を正規化する用途がある。

### 保守・注意

Unicodeは継続保守される。BCP47のRFC 5646本文は2009-09で、IANAレジストリは別途更新され得る。したがってタグ検証は古い固定表ではなく、IANA registryとUnicode CLDR等の適切なデータ源を使う。見た目が同じ文字の正規化、異体字、RTL、合成文字、検索安全性を考慮する。Unicode Consortiumの仕様本文・データの再利用条件はページごとに確認が必要で、本調査では詳細なライセンス条項はunknown。

## 10. 既存横断検索・集約基盤

### Europeana

Europeana公式APIページは、欧州数千機関からのデジタル化された美術、新聞、写真、動画、3D等を対象に、Search、Record、IIIF APIを使った検索・レコード取得・高解像度画像表示を案内する。新聞についてmillions of pages available as searchable full textと明記される。[14] 研究・大規模利用向けにSPARQL、OAI-PMH、dataset downloadsも案内される。[14]

- 全文検索: **可（少なくとも新聞等の公開範囲）**。
- OCR: **可否はコレクション／レコード依存**。全文がOCRか転写か、精度・本文取得形式は個別確認が必要。
- 画像: **可**（IIIF viewer向け高解像度画像）。
- ページ単位取得: **一部可と推測できるが、APIページだけでは全エンドポイント仕様を確認できずunknown**。IIIF Presentation/画像サービスの有無をレコード単位に確認する。
- IIIF: **可**。OAI-PMH: **可（大規模データ取得手段として公式案内）**。SRU: **公式ページでは確認できずunknown**。
- 利用条件: 無料API keyが必要。利用規約・データ提供機関ごとの権利表示を確認する。

EuropeanaはGlobal Library MCPと、複数機関を一つの検索・取得面に集約する点で重複する。一方Europeana固有のデータモデル、権利、APIキー、欧州文化遺産の収録範囲は置換できない。Global Library MCPは、Europeana等を共通MCPツールに束ねるadapterとして差別化するのが自然だが、現行MCPの接続先実装はunknown。

### WorldCat Search API（OCLC）

公式OpenAPI文書はWorldCat bibliographic resources検索、特定OCLC番号の取得、brief bibliographic search、other editions、member holdings、local holdings、shared print holdingsを提供する。検索結果スキーマにはtitle、creator、date、language、format、subject、description、abstract、open access link、digital object info等がある。[15]

- 全文検索: **bibliographic recordsの検索は可**。本文全文検索であるとは記載されておらず、全文はunknown。
- OCR: **unknown**。
- 画像: **unknown**。DigitalObjectInfo/OpenAccessLinkは存在するが、画像配信を保証しない。
- ページ単位取得: **不可／unknown**。API文書でデジタルページ画像取得は確認できない。
- IIIF/SRU/OAI-PMH: **WorldCat Search API仕様上は確認できずunknown**。別OCLC製品・機関実装との混同を避ける。
- ライセンス／認証／利用上限: API利用契約、認証、OCLC会員・サービス条件の確認が必要。公開文書だけでGlobal Library MCPへの再配布権を判断できない。

WorldCatは図書館の書誌・所蔵の横断検索が強く、Global Library MCPの書誌発見・所蔵照会と重複する可能性が高い。一方、WorldCatはOCLC管理の商用／契約APIであり、IIIF画像やOCR本文を必ずしも提供しない。Global Library MCPが文化遺産画像・全文・各機関APIを統合するなら、WorldCatは一接続先であって完全代替ではない。

### DPLA

DPLA公式Developerページは、公開APIでDPLAカタログのevery itemを検索・アクセスでき、bulk downloadとコード例・ライブラリも提供すると説明する。[16]

- 全文検索: **カタログ・レコード検索は可**。本文全文検索は公式ページだけでは確認できずunknown。
- OCR: **unknown**。
- 画像: **レコード内の提供機関リンク等に依存し、APIページだけでは画像配信を断定できずunknown**。
- ページ単位取得: **unknown**。
- IIIF/SRU/OAI-PMH: **公式Developerページでは確認できずunknown**。
- 利用範囲: APIとbulk downloadは広範な再利用を想定するが、個々の提供機関の権利・利用条件は個別に確認する。

DPLAは複数機関の米国文化遺産レコードを横断検索する点でGlobal Library MCPと重複する。APIとbulk downloadを一つのMCPインターフェースで提供する場合は、認証、ページング、ダウンロード負荷、権利表示を保持し、DPLAのデータを独自データとして再配布しない設計が必要。具体的なAPI v2仕様・レート制限・全文／IIIF対応は本調査ではunknown。

## 11. Global Library MCPとの重複・差分（現時点）

Global Library MCP固有の公式仕様、GitHubリポジトリ、Registry登録、ツール一覧、ライセンス、保守者、脅威モデルは本調査入力からは確認できず、以下は事実ではなく設計上の整理である。

- **重複し得る領域**: MCPは統一的なtools/resources/promptsの接続面、Europeana/DPLA/WorldCatは既に横断検索・集約、SRU/OAI-PMHは検索または収集、IIIFは画像・ページ・OCR annotation、MARC/DCはメタデータ正規化を担う。
- **差分候補**: Global Library MCPが機関ごとのAPIをMCPツールに変換し、共通検索、出典・権利・言語・ページ・画像URIを保ったまま返すなら、標準そのものや集約サービスの代替ではなくオーケストレーション層になる。
- **必須の境界**: MCPツールの全文検索と、SRU/OAI-PMH/IIIFの各接続先能力を混同しない。結果ごとにsource institution、protocol、record id、language、rights、confidence、retrieval timestamp、page/canvas、raw URLを保持する。
- **未確認**: Global Library MCPが既にどの接続先・検索フィールド・OCR・画像・ページ取得・ライセンスを実装しているか。重複判定を確定するには、実装リポジトリ・server.json・API schema・テスト・デプロイ設定が必要。

## References

[1]: https://github.com/modelcontextprotocol/modelcontextprotocol "Specification and documentation for the Model Context Protocol"
[2]: https://modelcontextprotocol.io/registry/about "The MCP Registry"
[3]: https://iiif.io/api/ "IIIF API Specifications"
[4]: https://iiif.io/api/search/2.0/ "IIIF Content Search API 2.0"
[5]: https://www.loc.gov/standards/sru/ "SRU: Search/Retrieval via URL"
[6]: https://www.openarchives.org/OAI/openarchivesprotocol.html "Open Archives Initiative Protocol for Metadata Harvesting v2.0"
[7]: https://www.dublincore.org/specifications/dublin-core/dcmi-terms/ "DCMI Metadata Terms"
[8]: https://www.dublincore.org/specifications/dublin-core/dcmi-terms/release_history/ "DCMI Metadata Terms Release History and licensing notice"
[9]: https://www.loc.gov/marc/ "MARC Standards"
[10]: https://www.loc.gov/standards/alto/ "ALTO Technical Metadata for Layout and Text Objects"
[11]: https://www.loc.gov/standards/mets/ "Metadata Encoding and Transmission Standard (METS)"
[12]: https://www.unicode.org/standard/standard.html "About the Unicode Standard"
[13]: https://www.rfc-editor.org/rfc/rfc5646 "RFC 5646: Tags for Identifying Languages"
[14]: https://api.europeana.eu/ "Europeana APIs"
[15]: https://developer.api.oclc.org/wcv2 "WorldCat Search API v2"
[16]: https://pro.dp.la/developers "DPLA Developers"
