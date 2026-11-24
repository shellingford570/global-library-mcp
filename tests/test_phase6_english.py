from global_library_mcp.question import analyze_question


def test_english_concepts_and_word_century():
    a = analyze_question("How did hydroelectric power develop in the early twentieth century?")
    assert "hydroelectric power" in a.core_concepts
    assert "twentieth" not in a.core_concepts
    assert a.era is not None and a.era["start"] == 1901 and a.era["end"] == 1935


def test_english_phrase_extraction():
    a = analyze_question("What did contemporary engineering books say about power transmission?")
    assert "power transmission" in a.core_concepts
    assert "books" not in a.core_concepts


def test_english_debris_and_region():
    a = analyze_question("When did telephone exchange service begin in Japan?")
    assert "begin" not in a.core_concepts
    assert "Japan" not in a.core_concepts
    assert "日本" in a.regions
    assert "telephone exchange service" in a.core_concepts


def test_english_meiji_era_name():
    a = analyze_question("How was electricity used in Meiji era factories?")
    assert a.era is not None and a.era["era"] == "明治"


def test_japanese_analysis_unchanged():
    a = analyze_question("明治時代の電信技術の導入について教えて")
    assert "電信技術" in a.core_concepts
    assert a.era is not None and a.era["era"] == "明治"
