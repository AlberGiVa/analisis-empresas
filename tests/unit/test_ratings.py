import pytest

from company_analysis.models.ratings import (
    WORST_INVESTMENT_GRADE_NOTCH,
    is_investment_grade,
    rating_notch,
)


@pytest.mark.parametrize(
    ("sp_fitch", "moodys", "notch"),
    [("AAA", "Aaa", 1), ("AA-", "Aa3", 4), ("A", "A2", 6), ("BBB-", "Baa3", 10), ("B+", "B1", 14)],
)
def test_both_notations_map_to_the_same_notch(sp_fitch: str, moodys: str, notch: int) -> None:
    assert rating_notch(sp_fitch) == rating_notch(moodys) == notch


def test_a_downgrade_increases_the_notch() -> None:
    assert rating_notch("BB+") == rating_notch("BBB-") + 1


def test_defaults_share_the_last_notch() -> None:
    assert rating_notch("D") == rating_notch("SD") == rating_notch("RD") == 22


def test_investment_grade_boundary() -> None:
    assert rating_notch("BBB-") == WORST_INVESTMENT_GRADE_NOTCH
    assert is_investment_grade("BBB-")
    assert not is_investment_grade("BB+")


def test_unknown_rating_is_rejected() -> None:
    with pytest.raises(ValueError, match="Rating no reconocido"):
        rating_notch("AAA+")
