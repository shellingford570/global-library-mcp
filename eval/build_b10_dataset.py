"""Build the b10 evaluation dataset (brief sections 7-8).

Generates ~260 cases in eight categories from a curated fact
table, split deterministically into dev / fixed / holdout
BEFORE any b10 tuning, and writes:

- eval/b10-dev.json, eval/b10-fixed.json, eval/b10-holdout.json
- eval/b10-dataset-manifest.json (SHA-256 per file, counts,
  label-provenance tally)
- eval/b10-review.csv (a human-review sheet: every case with
  empty reviewer columns, so independent human verification
  can be added later without changing the dataset)

Label provenance discipline (section 8): every case carries
label_provenance.source. Facts restated from standard
bibliographic records are marked bibliographic_source_supported
ONLY where the basis names the record type; everything else is
agent_assigned. NOTHING here is independent_human_verified -
no human has reviewed these labels, and the manifest says so.
Cases whose expectations concern authored snippets (claims,
contradictions) are self-consistent by construction and are
agent_assigned.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

CASES: list[dict] = []


def _split(case_id: str) -> str:
    digest = int(hashlib.sha256(case_id.encode("utf-8")).hexdigest(), 16)
    bucket = digest % 10
    return "dev" if bucket < 4 else "fixed" if bucket < 8 else "holdout"


def add(category: str, case: dict, provenance: str, basis: str) -> None:
    n = sum(1 for c in CASES if c["category"] == category) + 1
    case_id = f"b10-{category[:4]}-{n:03d}"
    CASES.append({
        "id": case_id,
        "category": category,
        "split": _split(case_id),
        **case,
        "label_provenance": {"source": provenance, "basis": basis},
    })


BIB = "bibliographic_source_supported"
AGT = "agent_assigned"
BIB_BASIS = ("standard bibliographic record fact (national-library "
             "catalogue data: author dates, first-edition year, "
             "original title) restated without alteration")
AGT_BASIS = "agent-assigned expectation; not human-reviewed"

# ---------------------------------------------------------------
# Category 1: author / work identification (40)
# (author, variants, years, trap) - traps: same surname,
# about-vs-by, translator, editor, pen name.
AUTHORS = [
    ("kant", "Immanuel Kant", ["カント", "イマヌエル・カント", "Kant, Immanuel"],
     (1724, 1804), "Kritik der reinen Vernunft"),
    ("darwin_c", "Charles Darwin", ["チャールズ・ダーウィン", "ダーウィン"],
     (1809, 1882), "On the Origin of Species"),
    ("darwin_e", "Erasmus Darwin", ["エラズマス・ダーウィン"],
     (1731, 1802), "Zoonomia"),
    ("newton", "Isaac Newton", ["アイザック・ニュートン", "ニュートン"],
     (1643, 1727), "Philosophiæ Naturalis Principia Mathematica"),
    ("weber_m", "Max Weber", ["マックス・ヴェーバー", "マックス・ウェーバー"],
     (1864, 1920), "Die protestantische Ethik"),
    ("weber_a", "Alfred Weber", ["アルフレート・ヴェーバー"],
     (1868, 1958), "Kulturgeschichte als Kultursoziologie"),
    ("rousseau", "Jean-Jacques Rousseau", ["ジャン＝ジャック・ルソー", "ルソー"],
     (1712, 1778), "Du contrat social"),
    ("fukuzawa", "福澤諭吉", ["福沢諭吉", "ふくざわ ゆきち"],
     (1835, 1901), "学問のすゝめ"),
    ("soseki", "夏目漱石", ["夏目金之助", "なつめ そうせき"],
     (1867, 1916), "吾輩は猫である"),
    ("ogai", "森鷗外", ["森鴎外", "森林太郎", "もり おうがい"],
     (1862, 1922), "舞姫"),
]
for key, name, variants, years, work in AUTHORS:
    add("author_work_identification", {
        "task": "identify_author",
        "prompt_form": variants[0],
        "expect": {"author": name, "birth_year": years[0],
                   "death_year": years[1], "known_work": work},
    }, BIB, BIB_BASIS)
    add("author_work_identification", {
        "task": "identify_author_from_variant",
        "prompt_form": variants[-1],
        "expect": {"author": name},
    }, BIB, BIB_BASIS)

TRAPS = [
    ("surname_only_darwin",
     "「ダーウィン」の著作を特定せよ(姓のみ)",
     "Charles Darwin と Erasmus Darwin の両候補を提示し、姓だけで確定しない"),
    ("surname_only_weber",
     "「ヴェーバー」の著作を特定せよ(姓のみ)",
     "Max Weber と Alfred Weber の両候補を提示し、姓だけで確定しない"),
    ("about_kant_not_by_kant",
     "カントの哲学を解説した研究書",
     "研究書を Kant 自身の著作と認定しない(著者は研究者)"),
    ("translator_not_author",
     "『純粋理性批判』の日本語訳者",
     "翻訳者を原著者 Kant と認定しない"),
    ("editor_not_chapter_author",
     "カント記念論文集の編者",
     "編者を全章の著者と認定しない"),
    ("pen_name_soseki",
     "夏目金之助の小説",
     "筆名 夏目漱石 と同一人物として扱う"),
    ("pen_name_ogai",
     "森林太郎の小説",
     "筆名 森鷗外 と同一人物として扱う"),
    ("old_script_fukuzawa",
     "福澤諭吉(旧字体表記)の著作",
     "新字体 福沢諭吉 と同一人物として扱う"),
    ("old_script_ogai",
     "森鷗外(鷗=旧字体)の著作",
     "森鴎外 と同一人物として扱う"),
    ("name_order_kant",
     "Kant, Immanuel(姓・名順)の著作",
     "Immanuel Kant と同一人物として扱う"),
    ("subject_person_not_author",
     "ダーウィンを論じた伝記の著者",
     "伝記の著者を Darwin 本人と認定しない"),
    ("grandfather_not_grandson",
     "エラズマス・ダーウィンの進化論的著作",
     "Charles Darwin の著作と統合しない(Zoonomia は祖父)"),
    ("brother_not_brother",
     "アルフレート・ヴェーバーの文化社会学",
     "Max Weber の著作と統合しない"),
    ("posthumous_editor",
     "死後に編纂されたカントの講義録",
     "編者を著者とせず、Kant の講義に基づく資料として区別する"),
    ("corporate_author",
     "文部省編の教科書",
     "機関著者を個人著者として扱わない"),
    ("same_name_different_person",
     "ジョン・スミス(別人同名)の著作",
     "同姓同名を無条件に統合しない"),
    ("initials_only",
     "J.-J. ルソーの著作",
     "Jean-Jacques Rousseau の候補として提示する"),
    ("kana_reading_only",
     "ふくざわゆきちの著作",
     "福澤諭吉 の候補として提示する"),
    ("work_attributed_later",
     "後世にカントの作とされた偽書",
     "真作と統合せず、帰属が疑わしい資料として区別する"),
    ("translation_editor_mix",
     "翻訳・監修を兼ねた日本語版の監修者",
     "監修者を原著者と認定しない"),
]
for key, prompt, expectation in TRAPS:
    add("author_work_identification", {
        "task": "author_trap", "trap_id": key, "prompt": prompt,
        "expect": {"required_behaviour": expectation},
    }, AGT, AGT_BASIS)

# ---------------------------------------------------------------
# Category 2: original / translated titles (30)
WORKS = [
    ("kant-kritik", "Kritik der reinen Vernunft",
     {"ja": ["純粋理性批判"], "en": ["Critique of Pure Reason"],
      "fr": ["Critique de la raison pure"]}, "Immanuel Kant", 1781),
    ("darwin-origin", "On the Origin of Species",
     {"ja": ["種の起源"], "de": ["Über die Entstehung der Arten"],
      "fr": ["De l'origine des espèces"]}, "Charles Darwin", 1859),
    ("marx-kapital", "Das Kapital",
     {"ja": ["資本論"], "en": ["Capital"], "fr": ["Le Capital"]},
     "Karl Marx", 1867),
    ("smith-wealth", "An Inquiry into the Nature and Causes of the Wealth of Nations",
     {"ja": ["国富論"], "de": ["Der Wohlstand der Nationen"]},
     "Adam Smith", 1776),
    ("rousseau-contrat", "Du contrat social",
     {"ja": ["社会契約論"], "en": ["The Social Contract"]},
     "Jean-Jacques Rousseau", 1762),
    ("newton-principia", "Philosophiæ Naturalis Principia Mathematica",
     {"ja": ["自然哲学の数学的諸原理", "プリンキピア"],
      "en": ["Mathematical Principles of Natural Philosophy"]},
     "Isaac Newton", 1687),
    ("goethe-faust", "Faust",
     {"ja": ["ファウスト"], "en": ["Faust"], "fr": ["Faust"]},
     "Johann Wolfgang von Goethe", 1808),
    ("dostoevsky-crime", "Преступление и наказание",
     {"ja": ["罪と罰"], "en": ["Crime and Punishment"],
      "de": ["Schuld und Sühne"]}, "Fyodor Dostoevsky", 1866),
    ("tolstoy-war", "Война и мир",
     {"ja": ["戦争と平和"], "en": ["War and Peace"],
      "de": ["Krieg und Frieden"]}, "Leo Tolstoy", 1869),
    ("hugo-miserables", "Les Misérables",
     {"ja": ["レ・ミゼラブル", "ああ無情"], "en": ["Les Misérables"]},
     "Victor Hugo", 1862),
]
for key, original, translations, author, year in WORKS:
    langs = sorted(translations)
    add("original_translated_title", {
        "task": "find_original_from_translation",
        "given_title": translations[langs[0]][0],
        "given_language": langs[0],
        "expect": {"work": key, "original_title": original,
                   "author": author},
    }, BIB, BIB_BASIS)
    add("original_translated_title", {
        "task": "find_translations_from_original",
        "given_title": original,
        "expect": {"work": key,
                   "translated_titles": translations},
    }, BIB, BIB_BASIS)
    add("original_translated_title", {
        "task": "work_identity_across_languages",
        "given_title": translations[langs[-1]][0],
        "given_language": langs[-1],
        "expect": {"work": key, "original_title": original,
                   "first_publication_year": year},
    }, BIB, BIB_BASIS)

# ---------------------------------------------------------------
# Category 3: historical notation (30)
HISTORICAL = [
    ("蒸氣機關", "蒸気機関"), ("水力發電", "水力発電"), ("鐵道", "鉄道"),
    ("學術", "学術"), ("電氣", "電気"), ("發電所", "発電所"),
    ("機關車", "機関車"), ("歐洲", "欧州"), ("亞細亞", "亜細亜"),
    ("獨逸", "ドイツ"), ("佛蘭西", "フランス"), ("露西亞", "ロシア"),
    ("英吉利", "イギリス"), ("澤山", "沢山"), ("廣島", "広島"),
    ("櫻", "桜"), ("龍", "竜"), ("國語", "国語"), ("讀本", "読本"),
    ("思ふ", "思う"), ("言ふ", "言う"), ("ゐる", "いる"),
    ("steam-engine", "steam engine"), ("aeroplane", "airplane"),
    ("Dampfmaſchine", "Dampfmaschine"),
    ("Dampfmafchine", "Dampfmaschine"),
    ("sçavoir", "savoir"), ("connoître", "connaître"),
    ("œuvre", "oeuvre"), ("gaol", "jail"),
]
for old, new in HISTORICAL:
    add("historical_notation", {
        "task": "historical_form_search",
        "historical_form": old,
        "expect": {"modern_form": new,
                   "rule": "正規化は検索補助のみ;原文・逐語引用は改変しない"},
    }, AGT, AGT_BASIS)

# ---------------------------------------------------------------
# Category 4: multilingual subject search (40)
CONCEPTS = [
    ("steam_engine", {"ja": "蒸気機関", "en": "steam engine",
                      "de": "Dampfmaschine", "fr": "machine à vapeur",
                      "fi": "höyrykone", "sv": "ångmaskin",
                      "nl": "stoommachine"}),
    ("hydroelectric", {"ja": "水力発電", "en": "hydroelectric power",
                       "de": "Wasserkraft", "fr": "énergie hydraulique",
                       "fi": "vesivoima", "sv": "vattenkraft",
                       "nl": "waterkracht"}),
    ("railway", {"ja": "鉄道", "en": "railway", "de": "Eisenbahn",
                 "fr": "chemin de fer", "fi": "rautatie",
                 "sv": "järnväg", "nl": "spoorweg"}),
    ("printing", {"ja": "印刷", "en": "printing", "de": "Buchdruck",
                  "fr": "imprimerie", "fi": "kirjapaino",
                  "sv": "boktryckeri", "nl": "boekdrukkunst"}),
    ("sericulture", {"ja": "養蚕", "en": "sericulture",
                     "de": "Seidenraupenzucht", "fr": "sériciculture",
                     "fi": "silkkiäistoukan kasvatus",
                     "sv": "silkesodling", "nl": "zijdeteelt"}),
    ("vaccination", {"ja": "種痘", "en": "vaccination",
                     "de": "Pockenimpfung", "fr": "vaccination",
                     "fi": "isorokkorokotus", "sv": "vaccination",
                     "nl": "inenting"}),
    ("telegraph", {"ja": "電信", "en": "telegraph", "de": "Telegraf",
                   "fr": "télégraphe", "fi": "lennätin",
                   "sv": "telegraf", "nl": "telegraaf"}),
    ("textile_mill", {"ja": "紡績", "en": "textile mill",
                      "de": "Spinnerei", "fr": "filature",
                      "fi": "kehruutehdas", "sv": "spinneri",
                      "nl": "spinnerij"}),
    ("lighthouse", {"ja": "灯台", "en": "lighthouse", "de": "Leuchtturm",
                    "fr": "phare", "fi": "majakka", "sv": "fyr",
                    "nl": "vuurtoren"}),
    ("canal", {"ja": "運河", "en": "canal", "de": "Kanal",
               "fr": "canal", "fi": "kanava", "sv": "kanal",
               "nl": "kanaal"}),
]
LANG_ROTATION = ["en", "de", "fr", "ja"]
for key, labels in CONCEPTS:
    for lang in LANG_ROTATION:
        add("multilingual_subject", {
            "task": "subject_search_from_language",
            "query_language": lang, "query_term": labels[lang],
            "expect": {"concept": key,
                       "labels": labels,
                       "rule": "原語クエリは必ず実行;他言語ラベルは発見用展開"},
        }, AGT, AGT_BASIS)

# ---------------------------------------------------------------
# Category 5: edition identification (30)
EDITIONS = [
    ("kant-kritik-A", "Kritik der reinen Vernunft", 1781, "第1版(A版)"),
    ("kant-kritik-B", "Kritik der reinen Vernunft", 1787, "第2版(B版)"),
    ("darwin-origin-1", "On the Origin of Species", 1859, "初版"),
    ("darwin-origin-6", "On the Origin of Species", 1872, "第6版"),
    ("newton-principia-1", "Principia", 1687, "初版"),
    ("newton-principia-3", "Principia", 1726, "第3版"),
    ("goethe-faust-1", "Faust. Eine Tragödie", 1808, "第一部"),
    ("goethe-faust-2", "Faust. Der Tragödie zweiter Teil", 1832, "第二部"),
]
for key, title, year, label in EDITIONS:
    add("edition_identification", {
        "task": "distinguish_edition",
        "title": title, "year": year,
        "expect": {"edition": key, "edition_label": label,
                   "rule": "同一作品でも版が異なればページ・OCR・引用を共有しない"},
    }, BIB, BIB_BASIS)
MERGE_TRAPS = [
    ("kant-A-vs-B", "1781年版と1787年版の『純粋理性批判』",
     "同一作品の異なる版として区別し、統合しない"),
    ("origin-1-vs-6", "1859年版と1872年版の『種の起源』",
     "同一作品の異なる版として区別し、統合しない"),
    ("origin-vs-ja-translation", "『種の起源』英語原著と日本語訳",
     "原著と翻訳版を別表現として区別する"),
    ("genji-translations", "源氏物語の Waley 訳と Tyler 訳",
     "同一作品の異なる翻訳として区別する"),
    ("genji-vs-modern-ja", "源氏物語の原文と谷崎潤一郎の現代語訳",
     "原文と現代語訳を別表現として区別する"),
    ("principia-editions", "プリンキピア初版と第3版",
     "同一作品の異なる版として区別し、統合しない"),
    ("faust-parts", "ファウスト第一部と第二部",
     "同一作品の異なる部として区別し、一方の引用を他方に使わない"),
    ("reprint-vs-revised", "復刻版と改訂版",
     "復刻(同一版の再刊)と改訂(内容変更)を区別する"),
    ("abridged-vs-full", "抄訳と全訳",
     "抄訳を全訳と同一視しない"),
    ("same-year-different-publisher", "同年刊行の異なる出版者の版",
     "出版者が異なれば別資料として扱う"),
    ("volume-split", "分冊刊行の第1巻と第2巻",
     "巻を混同せず、引用は巻・ページで特定する"),
    ("newspaper-vs-book", "新聞連載版と単行本版",
     "掲載形態の異なる版として区別する"),
]
for key, prompt, expectation in MERGE_TRAPS:
    add("edition_identification", {
        "task": "must_not_merge", "trap_id": key, "prompt": prompt,
        "expect": {"required_behaviour": expectation},
    }, AGT, AGT_BASIS)
for i in range(10):
    key, title, year, label = EDITIONS[i % len(EDITIONS)]
    add("edition_identification", {
        "task": "edition_from_year_and_title",
        "title": title, "year": year,
        "expect": {"edition": key},
    }, BIB, BIB_BASIS)

# ---------------------------------------------------------------
# Category 6: historical claims and evidence (40)
# Expectations concern the AUTHORED snippets: self-consistent.
CLAIMS = [
    ("meiji-hydro", "明治時代の日本で水力発電所が建設された",
     {"subject": "日本", "event": "水力発電所の建設", "era": "明治"},
     [("1891年の京都・蹴上発電所の営業運転開始を伝える資料",
       "supported_candidate"),
      ("1925年に明治期の発電事業を回顧した資料", "contextual_only"),
      ("江戸時代の水車利用を述べた資料", "insufficient_evidence")]),
    ("railway-1872", "日本の鉄道は1872年に開業した",
     {"subject": "日本", "event": "鉄道開業", "year": 1872},
     [("1872年の新橋・横浜間開業を報じる資料", "supported_candidate"),
      ("1889年の東海道線全通を報じる資料", "contextual_only")]),
    ("origin-1859", "『種の起源』は1859年に刊行された",
     {"work": "On the Origin of Species", "year": 1859},
     [("1859年刊行の初版の書誌情報", "supported_candidate"),
      ("1872年刊行の第6版の書誌情報", "contextual_only")]),
    ("steam-japan", "明治初期の日本に蒸気機関が導入された",
     {"subject": "日本", "topic": "蒸気機関", "era": "明治初期"},
     [("明治期の蒸気機関導入を記した同時代資料", "supported_candidate"),
      ("幕末の蒸気船来航を記した資料", "contextual_only")]),
    ("printing-gutenberg", "グーテンベルクの活版印刷は15世紀半ばに始まった",
     {"person": "Gutenberg", "topic": "活版印刷", "century": 15},
     [("1450年代のマインツ印刷を記した資料", "supported_candidate"),
      ("中国の木版印刷を記した資料", "insufficient_evidence")]),
    ("telegraph-japan", "日本で電信が実用化されたのは明治初期である",
     {"subject": "日本", "topic": "電信", "era": "明治初期"},
     [("1869年の東京・横浜間電信開通を記した資料", "supported_candidate"),
      ("1876年の電話導入を記した資料", "contextual_only"),
      ("江戸時代の飛脚制度を記した資料", "insufficient_evidence"),
      ("明治後期の無線電信実験を記した資料", "contextual_only")]),
]
for key, statement, structure, snippets in CLAIMS:
    for text, expected in snippets:
        add("claim_evidence", {
            "task": "claim_snippet_match",
            "claim_id": key, "statement": statement,
            "structure": structure,
            "snippet": text,
            "expect": {"evidence_state": expected,
                       "rule": "語彙一致だけで supported に昇格させない"},
        }, AGT, AGT_BASIS)
NUMERIC_CLAIMS = [
    ("capacity-mismatch", "発電所の出力は500キロワットであった",
     "原文の数値は 500 馬力", "insufficient_evidence",
     "単位が異なる数値を一致とみなさない"),
    ("year-mismatch", "発電所は明治30年に完成した",
     "原文は明治13年の完成と記す", "conflicting_candidate",
     "年代の不一致を矛盾候補として示す"),
    ("place-mismatch", "発電所は京都に建設された",
     "原文は仙台の発電所について述べる", "insufficient_evidence",
     "地名の不一致を支持根拠にしない"),
    ("quantity-missing", "鉄道は全長30キロメートルであった",
     "原文に距離の記載がない", "insufficient_evidence",
     "原文にない数値を補わない"),
    ("negation", "この地域では水力発電は行われなかった",
     "原文は水力発電の実施を記す", "conflicting_candidate",
     "否定表現を見落として支持としない"),
]
for key, statement, snippet, expected, rule in NUMERIC_CLAIMS:
    add("claim_evidence", {
        "task": "claim_numeric_match", "claim_id": key,
        "statement": statement, "snippet": snippet,
        "expect": {"evidence_state": expected, "rule": rule},
    }, AGT, AGT_BASIS)
for i in range(20):
    key, statement, structure, snippets = CLAIMS[i % len(CLAIMS)]
    text, expected = snippets[i % len(snippets)]
    add("claim_evidence", {
        "task": "claim_structure_extraction",
        "claim_id": f"{key}-struct-{i}",
        "statement": statement,
        "expect": {"structure": structure,
                   "rule": "主張の構造化は真偽判定ではない;"
                           "原文にない主体・時代・数値を補わない"},
    }, AGT, AGT_BASIS)

# ---------------------------------------------------------------
# Category 7: contradiction / difference classification (20)
CONTRA = [
    ("unit-difference", "出力500馬力", "出力373キロワット",
     "differing_unit", "馬力とキロワットは換算可能であり矛盾ではない"),
    ("scope-difference", "管内の発電所は12か所", "全国の発電所は300か所",
     "differing_scope", "集計範囲が異なる"),
    ("time-difference", "明治20年の鉄道延長", "明治40年の鉄道延長",
     "differing_time", "時点が異なる"),
    ("notation-difference", "水力發電", "水力発電",
     "consistent_candidate", "旧字体と新字体の表記差"),
    ("translation-difference", "蒸気機関", "steam engine",
     "consistent_candidate", "翻訳による表記差"),
    ("definition-difference", "発電所(水力のみ)", "発電所(火力を含む)",
     "differing_scope", "定義範囲が異なる"),
    ("true-contradiction-1", "開業は1872年", "開業は1882年",
     "contradiction_candidate", "同対象・同時点で年が異なる"),
    ("true-contradiction-2", "出力は500キロワット", "出力は800キロワット",
     "contradiction_candidate", "同対象・同単位で数値が異なる"),
    ("ocr-suspect", "明治36年", "明治86年",
     "contradiction_candidate", "OCR誤認の可能性を併記する"),
    ("insufficient-context", "延長は30里", "延長は延びた",
     "insufficient_context", "数値情報が不足し比較できない"),
]
for key, a, b, expected, note in CONTRA:
    add("contradiction", {
        "task": "classify_difference", "pair_id": key,
        "statement_a": a, "statement_b": b,
        "expect": {"classification": expected, "note": note,
                   "rule": "意味的矛盾が独立検証されない限り"
                           "contradiction_confirmed としない"},
    }, AGT, AGT_BASIS)
for i in range(10):
    key, a, b, expected, note = CONTRA[i % len(CONTRA)]
    add("contradiction", {
        "task": "classify_difference_reversed", "pair_id": f"{key}-rev",
        "statement_a": b, "statement_b": a,
        "expect": {"classification": expected},
    }, AGT, AGT_BASIS)

# ---------------------------------------------------------------
# Category 8: false premises / negative cases (30)
FALSE_PREMISES = [
    "明治時代のテレビ放送に関する資料",
    "大正時代に普及した家庭用電気冷蔵庫の広告",
    "江戸時代の蒸気機関車の営業運行記録",
    "ダーウィンが書いた『資本論』",
    "カントが提唱した相対性理論",
    "夏目漱石による『源氏物語』の現代語訳",
    "福澤諭吉が書いた『吾輩は猫である』",
    "ニュートンが書いた『種の起源』",
    "1900年の日本におけるインターネット利用統計",
    "明治時代の飛行機による旅客輸送の記録",
    "紫式部が刊行した印刷版『源氏物語』の初版",
    "シェイクスピアが書いた映画の脚本",
    "ベートーヴェンの演奏を収めたレコード",
    "ガリレオが望遠鏡で観測した冥王星の記録",
    "コペルニクスが唱えた進化論",
    "森鷗外が書いた『こころ』",
    "エジソンが発明した蒸気機関",
    "ワットが発明した電球",
    "奈良時代の活版印刷所の記録",
    "平安時代に発行された日刊新聞",
    "1905年の日本におけるカラーテレビ放送",
    "戦国時代の機関銃を装備した鉄砲隊",
    "アインシュタインが発明した電話",
    "キュリー夫人が発見したペニシリン",
    "フレミングが行った放射能研究",
    "ダーウィンが発見した万有引力の法則",
    "マルクスが書いた『種の起源』",
    "ヴォルテールが書いた『社会契約論』",
    "1889年に開通した日本の地下鉄",
    "明治5年に開業した新幹線",
]
for prompt in FALSE_PREMISES:
    add("false_premise_negative", {
        "task": "false_premise_handling",
        "prompt": prompt,
        "expect": {"required_behaviour":
                   "誤った前提を指摘し、前提に合致する根拠を採用しない;"
                   "関連資料の発見と前提の成立を混同しない"},
    }, AGT, AGT_BASIS)


def main() -> None:
    by_split: dict[str, list[dict]] = {"dev": [], "fixed": [], "holdout": []}
    for case in CASES:
        by_split[case["split"]].append(case)
    manifest: dict = {"total": len(CASES), "files": {},
                      "provenance_tally": {},
                      "independent_human_verified": 0,
                      "note": ("No case in this dataset is "
                               "independent_human_verified; see "
                               "label_provenance per case.")}
    for split, cases in by_split.items():
        path = ROOT / f"b10-{split}.json"
        payload = {"dataset": f"b10-{split}", "cases": cases}
        text = json.dumps(payload, ensure_ascii=False, indent=1)
        path.write_text(text, encoding="utf-8")
        manifest["files"][f"b10-{split}.json"] = {
            "cases": len(cases),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
    for case in CASES:
        src = case["label_provenance"]["source"]
        manifest["provenance_tally"][src] = \
            manifest["provenance_tally"].get(src, 0) + 1
    (ROOT / "b10-dataset-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1),
        encoding="utf-8")
    with open(ROOT / "b10-review.csv", "w", encoding="utf-8",
              newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "category", "split", "task",
                         "prompt_or_statement", "expected_summary",
                         "label_source", "reviewer", "review_outcome",
                         "review_notes"])
        for case in CASES:
            prompt = case.get("prompt") or case.get("statement") \
                or case.get("prompt_form") or case.get("given_title") \
                or case.get("historical_form") or case.get("title") or ""
            writer.writerow([
                case["id"], case["category"], case["split"],
                case.get("task", ""), prompt,
                json.dumps(case.get("expect", {}), ensure_ascii=False),
                case["label_provenance"]["source"], "", "", ""])
    print(f"total {len(CASES)} cases; splits: "
          + ", ".join(f"{k}={len(v)}" for k, v in by_split.items()))
    print("provenance:", manifest["provenance_tally"])


if __name__ == "__main__":
    main()
