import pytest

from sorrydb.runners.strategies import extract_proof_from_full_theorem_statement


@pytest.mark.parametrize(
    "stmt,expected",
    [
        ("theorem foo : 1 + 1 = 2 := by trivial", "trivial"),
        (
            "theorem bar : 1 + 1 = 2 ^\n    2 + 2 = 4 := by proof",
            "proof",
        ),
        (
            "lemma baz :\n    a = b\n    c = d := by my_proof",
            "my_proof",
        ),
        ("example : 2 = 2 := by rfl", "rfl"),
    ],
)
def test_extract_proof_from_full_theorem_statement(stmt, expected):
    assert extract_proof_from_full_theorem_statement(stmt) == expected
