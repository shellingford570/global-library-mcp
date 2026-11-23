from global_library_mcp.question import ERAS, normalize_text
from global_library_mcp.temporal import anchor_class, onset_after_era, sentence_years

MEIJI = {"era": "明治", "start": ERAS["明治"][0], "end": ERAS["明治"][1]}
TAISHO = {"era": "大正", "start": ERAS["大正"][0], "end": ERAS["大正"][1]}


def test_era_year_conversion():
    assert sentence_years(normalize_text("明治四十三年")) == [1910]
    assert sentence_years(normalize_text("大正十四年")) == [1925]
    assert sentence_years(normalize_text("1927年")) == [1927]


def test_anchor_classes():
    assert anchor_class(normalize_text("明治時代の出来事である"), MEIJI) == "in_era"
    assert anchor_class(normalize_text("昭和二年に開業した"), MEIJI) == "after_era"
    assert anchor_class(normalize_text("江戸時代の制度である"), MEIJI) == "before_era"
    assert anchor_class(normalize_text("特に年代の言及はない"), MEIJI) == "none"


def test_onset_after_era_detects_later_opening():
    sentences = [normalize_text("地下鉄は昭和二年に開業した")]
    assert onset_after_era(sentences, MEIJI) == sentences
    in_era = [normalize_text("鉄道は明治五年に開業した")]
    assert onset_after_era(in_era, MEIJI) == []
    assert onset_after_era(sentences, TAISHO) == sentences  # 1927 is after Taisho too
