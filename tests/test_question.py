from global_library_mcp.question import analyze_question, concept_variants, find_concept, normalize_text


def test_normalize_old_forms():
    assert normalize_text("發電") == normalize_text("発電")
    assert normalize_text("電氣") == normalize_text("電気")
    assert normalize_text("鐵道") == normalize_text("鉄道")
    assert "い" in normalize_text("ゐる")


def test_smartphone_question_analysis():
    analysis = analyze_question("明治時代のスマートフォンの普及について教えて")
    assert "スマートフォン" in analysis.core_concepts
    assert analysis.era is not None and analysis.era["era"] == "明治"
    assert "普及" in analysis.generic_terms
    assert any(r["type"] == "core_concept" and r["concept"] == "スマートフォン" for r in analysis.requirements)


def test_hydroelectric_question_analysis():
    analysis = analyze_question("明治時代の水力発電技術の発達について教えて")
    assert "水力発電" in analysis.core_concepts
    assert analysis.era["era"] == "明治"
    assert analysis.intent == "explanation"


def test_era_year_conversion():
    analysis = analyze_question("明治四十三年の発電水力調査について教えて")
    assert analysis.era["year"] == 1910


def test_numeric_intent_and_region():
    analysis = analyze_question("ペリー来航時の横浜村の正確な人口を教えて")
    assert analysis.intent == "numeric"
    assert any(r["type"] == "numeric" for r in analysis.requirements)
    us = analyze_question("ペリー来航に関するアメリカ側の記録について教えて")
    assert "米国" in us.regions


def test_comparison_and_cause_intents():
    assert analyze_question("明治と大正の水力発電を比較して").intent == "comparison"
    assert analyze_question("脚気が流行した原因は何か").intent == "cause"


def test_concept_matching_variants():
    text = normalize_text("發電水力の開發は臨時發電水力調査局が担った")
    assert find_concept(text, "発電") is not None
    assert find_concept(text, "水力発電") is not None  # via 發電水力? no - see below


def test_concept_matching_synonyms_and_english():
    assert find_concept(normalize_text("水力電気の送電について"), "水力発電") is not None
    assert find_concept(normalize_text("Hydroelectric power generation"), "水力発電") is not None
    assert find_concept(normalize_text("The telegraph arrived"), "電信") is not None
    assert find_concept(normalize_text("電話の歴史"), "電信") is None  # different concepts stay different


def test_variants_do_not_merge_distinct_concepts():
    assert "電話" not in concept_variants("電信")
    turbine = concept_variants("水車")
    assert "turbine" not in turbine  # weak link only, not a variant
