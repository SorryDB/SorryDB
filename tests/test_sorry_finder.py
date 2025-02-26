from sorryscraper.crawler.sorry_finder import find_sorry_lines


def test_find_sorry_lines():
    # Basic sorry statement
    basic_content = "def foo := sorry"
    basic_result = find_sorry_lines(basic_content)
    assert len(basic_result) == 1
    assert basic_result[0]["line_number"] == 1
    assert basic_result[0]["content"] == "def foo := sorry"


    # Multiline content
    multiline_content = (
        "theorem RiemannHypothesis : ∀ (s : ℂ) (_ : riemannZeta s = 0)\n"
        "(_ : ¬∃ n : ℕ, s = -2 * (n + 1)) (_ : s ≠ 1), s.re = 1 / 2 :=\n"
        "sorry"
    )
    results_multiline = find_sorry_lines(multiline_content)
    assert len(results_multiline) == 1

    # Multiple sorries
    multiple_sorry_content = (
        "theorem t1 := sorry\n"
        "-- sorry in comment\n"
        "theorem t2 := sorry"
    )
    multiple_sorry_result = find_sorry_lines(multiple_sorry_content)
    assert len(multiple_sorry_result) == 2
    assert multiple_sorry_result[0]["line_number"] == 1
    assert multiple_sorry_result[1]["line_number"] == 3

    # Commented sorries should be ignored
    comment_content = (
        "-- sorry\n"
        "/-- sorry -/\n"
        "theorem t1 := proof"
    )
    comment_result = find_sorry_lines(comment_content)
    assert len(comment_result) == 0

    # Word containing 'sorry' but not the token
    sorry_word = "theorem notsorryhere := proof"
    sorry_word_result = find_sorry_lines(sorry_word)
    assert len(sorry_word_result) == 0
