from datetime import datetime, timedelta

from trade_review.analyzer import AnalyzerConfig, detect_second_dip
from trade_review.models import IntradayPoint


def p(minute: int, price: float) -> IntradayPoint:
    return IntradayPoint(datetime(2024, 6, 13, 10, 0) + timedelta(minutes=minute), price, 100)


def test_detect_second_dip_with_rebound_height():
    points = [
        p(0, 10.0),
        p(1, 9.8),
        p(2, 10.1),
        p(3, 10.4),
        p(4, 10.0),
        p(5, 9.85),
        p(6, 9.9),
    ]

    pattern = detect_second_dip(points, datetime(2024, 6, 13, 10, 5), AnalyzerConfig())

    assert pattern is not None
    assert pattern.first_low_price == 9.8
    assert pattern.second_low_price == 9.85
    assert pattern.rebound_pct > 0.006


def test_detect_second_dip_requires_clear_structure():
    points = [p(0, 10.0), p(1, 9.9), p(2, 9.85), p(3, 9.8)]

    pattern = detect_second_dip(points, datetime(2024, 6, 13, 10, 3), AnalyzerConfig())

    assert pattern is None
