"""Percentile ranks within a peer group."""

from bisect import bisect_left, bisect_right
from collections.abc import Mapping


def percentile_ranks(values: Mapping[str, float], *, higher_is_better: bool) -> dict[str, float]:
    """Percentile rank (0-100) of each value in the group, where 100 is the best.

    Classic definition: (values worse than it + half of the values equal to it, itself
    included) / group size x 100. Ties share the same rank, and a group of one gives 50.
    """
    ordered = sorted(values.values())
    size = len(ordered)
    ranks = {}
    for key, value in values.items():
        below = bisect_left(ordered, value)
        equal = bisect_right(ordered, value) - below
        above = size - below - equal
        worse = below if higher_is_better else above
        ranks[key] = (worse + 0.5 * equal) / size * 100
    return ranks
