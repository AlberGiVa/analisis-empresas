"""Scatter chart of the study report: axis ticks and tooltips in each metric's unit."""

import pytest

from company_analysis.metrics.base import Unit
from company_analysis.reports.study import chart_svg

Point = tuple[str, str, float, float]
# x from 0 to 0,3 × 1,08 = 0,324 gives ticks every 0,1; y from 0 to 2,5 × 1,1 = 2,75, every 1.
POINTS: list[Point] = [("ZZAA", "Zeta Foods Inc.", 0.2, 1.5), ("ZZBB", "Beta Home Corp.", 0.3, 2.5)]


def test_a_percent_axis_reads_in_percent() -> None:
    svg = str(chart_svg(POINTS, "Margen EBITDA", "Deuda neta/EBITDA", x_unit=Unit.PERCENT))
    for tick in ("0 %", "10 %", "20 %", "30 %", "0,0x", "1,0x", "2,0x", "3,0x"):
        assert f">{tick}</text>" in svg
    assert ">0,1x</text>" not in svg
    assert "<title>Zeta Foods Inc.: 20,0 % · 1,5x</title>" in svg
    assert "<title>Beta Home Corp.: 30,0 % · 2,5x</title>" in svg


def test_both_axes_are_multiples_by_default() -> None:
    svg = str(chart_svg(POINTS, "EV/EBITDA", "Deuda neta/EBITDA"))
    for tick in ("0,0x", "0,1x", "0,2x", "0,3x"):
        assert f">{tick}</text>" in svg
    assert " %</text>" not in svg
    assert "<title>Zeta Foods Inc.: 0,2x · 1,5x</title>" in svg


@pytest.mark.parametrize("points", [[], POINTS[:1]])
def test_fewer_than_two_companies_give_a_message_instead_of_a_chart(points: list[Point]) -> None:
    html = str(chart_svg(points, "Margen EBITDA", "Deuda neta/EBITDA", x_unit=Unit.PERCENT))
    assert "No hay suficientes empresas" in html
    assert "<svg" not in html
