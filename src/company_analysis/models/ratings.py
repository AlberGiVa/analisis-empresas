"""Credit rating scale: maps S&P/Fitch and Moody's notation to a common notch number.

Notch 1 is the best rating (AAA/Aaa) and 22 is default (D). A higher notch means a worse rating,
so a downgrade is an increase in the notch number.
"""

from typing import Annotated

from pydantic import AfterValidator

_SP_FITCH = (
    "AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+",
    "BB", "BB-", "B+", "B", "B-", "CCC+", "CCC", "CCC-", "CC", "C", "D",
)  # fmt: skip
_MOODYS = (
    "Aaa", "Aa1", "Aa2", "Aa3", "A1", "A2", "A3", "Baa1", "Baa2", "Baa3", "Ba1",
    "Ba2", "Ba3", "B1", "B2", "B3", "Caa1", "Caa2", "Caa3", "Ca", "C",
)  # fmt: skip

_NOTCHES: dict[str, int] = {
    **{rating: notch for notch, rating in enumerate(_SP_FITCH, start=1)},
    **{rating: notch for notch, rating in enumerate(_MOODYS, start=1)},
    "SD": 22,  # selective default (S&P)
    "RD": 22,  # restricted default (Fitch)
}

WORST_INVESTMENT_GRADE_NOTCH = 10  # BBB- / Baa3


def rating_notch(rating: str) -> int:
    """Notch number of a rating (1 = AAA … 22 = D). Raises ``ValueError`` if unknown."""
    try:
        return _NOTCHES[rating]
    except KeyError:
        raise ValueError(f"Rating no reconocido: {rating!r}") from None


def is_investment_grade(rating: str) -> bool:
    return rating_notch(rating) <= WORST_INVESTMENT_GRADE_NOTCH


def _validate_rating(value: str) -> str:
    rating_notch(value)
    return value


RatingCode = Annotated[str, AfterValidator(_validate_rating)]
