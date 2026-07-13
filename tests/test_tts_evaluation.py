from content.evaluations.tts.cases import evaluation_cases


def test_evaluation_covers_required_case_counts() -> None:
    cases = evaluation_cases()
    assert sum(case.category == "letter" for case in cases) == 26
    assert sum(case.category == "vocabulary" for case in cases) == 30
    assert sum(case.category == "connected_speech" for case in cases) == 20
    assert sum(case.category == "article_sentence" for case in cases) == 20
