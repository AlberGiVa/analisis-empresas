import pytest

from company_analysis.scoring import percentile_ranks


def test_higher_is_better() -> None:
    ranks = percentile_ranks({"A": 10.0, "B": 20.0, "C": 30.0, "D": 40.0}, higher_is_better=True)
    # (values worse + half of the equal ones, itself included) / 4 x 100
    assert ranks == pytest.approx({"A": 12.5, "B": 37.5, "C": 62.5, "D": 87.5})


def test_lower_is_better() -> None:
    ranks = percentile_ranks({"A": 10.0, "B": 20.0, "C": 30.0, "D": 40.0}, higher_is_better=False)
    assert ranks == pytest.approx({"A": 87.5, "B": 62.5, "C": 37.5, "D": 12.5})


def test_ties_share_the_same_rank() -> None:
    ranks = percentile_ranks({"A": 1.0, "B": 2.0, "C": 2.0, "D": 3.0}, higher_is_better=True)
    assert ranks == pytest.approx({"A": 12.5, "B": 50.0, "C": 50.0, "D": 87.5})


def test_a_single_value_is_in_the_middle() -> None:
    assert percentile_ranks({"A": 5.0}, higher_is_better=True) == {"A": 50.0}
