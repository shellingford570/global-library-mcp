"""Deterministic fixture evaluation for the relevance gate.

No network: each case pairs a question with a fixed OCR page and the
gate outcome the Phase 4 brief requires. These fixtures are the
reproducible half of the evaluation; the live half is
eval/run_evaluation.py.
"""
import pytest

from global_library_mcp.question import analyze_question
from global_library_mcp.relevance import assess_relevance

CASES = [
    # (question, ocr_text, publication_year, expected_status)
    ("明治時代のスマートフォンの普及について教えて",
     "明治時代の通信手段として電信が普及し、通信の歴史に記録が残る。電話もやがて導入された。", 1905, "irrelevant"),
    ("明治時代の水力発電技術の発達について教えて",
     "發電水力の開發は明治四十三年に始まり、水力發電の適地が調査された。", 1911, "relevant"),
    ("發電水力の開發について教えてください",
     "發電水力の開發は明治四十三年に始まり、臨時發電水力調査局が担った事業である。", 1911, "relevant"),
    ("水力発電の仕組みについて教えて",
     "Hydroelectric power generation converts the energy of falling water into electricity.", 1909, "relevant"),
    ("明治時代の電話の歴史について教えて",
     "電信は明治二年に始まり、東京と横浜を結んだ。電信の歴史は通信の始まりである。", 1900, "irrelevant"),
    ("ペリー来航時の横浜村の正確な人口を教えて",
     "横浜村は小さな漁村であった。ペリー来航により開港し、村は大きく変化した。", 1900, "partially_relevant"),
    ("明治時代の原子力発電所の建設について教えて",
     "発電所の建設は明治時代に進み、電灯が普及した。発電の歴史は石炭から始まった。", 1910, "irrelevant"),
    # The page covers the topic （発電理論） but never the named person:
    # partially_relevant - shown as reference material, never evidence.
    ("山田電之助の発電理論について教えて",
     "発電の理論は多くの技術者により研究され、発電機の改良が進んだ記録がある。", 1912, "partially_relevant"),
    ("1891年の濃尾地震の被害について教えて",
     "濃尾地震は明治二十四年に発生し、大きな被害をもたらした。地震の記録が残されている。", 1892, "relevant"),
    ("明治時代の種痘の普及について教えて",
     "種痘は牛痘を用いる方法で、各地に広まった。種痘の普及は医学の発展に寄与した。", 1880, "relevant"),
]


@pytest.mark.parametrize("question,text,year,expected", CASES)
def test_gate_fixtures(question, text, year, expected):
    result = assess_relevance(analyze_question(question), text, publication_year=year)
    assert result["status"] == expected, f"{question}: {result}"
