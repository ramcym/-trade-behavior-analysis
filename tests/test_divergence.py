from datetime import datetime, timedelta

import pandas as pd

from trade_review.divergence import (
    DivergenceConfig,
    DailyIndexBar,
    detect_index_divergences,
    load_daily_index,
)


def bar(day: int, close: float, high: float | None = None, low: float | None = None) -> DailyIndexBar:
    return DailyIndexBar(
        date=datetime(2024, 1, 1) + timedelta(days=day),
        open=close,
        high=high if high is not None else close,
        low=low if low is not None else close,
        close=close,
        volume=1000,
    )


def test_detects_bottom_divergence_with_rsi():
    bars = [
        bar(0, 10.0),
        bar(1, 9.5),
        bar(2, 9.0),
        bar(3, 9.4),
        bar(4, 9.8),
        bar(5, 9.6),
        bar(6, 9.2),
        bar(7, 8.8),
        bar(8, 9.3),
        bar(9, 9.9),
    ]

    points = detect_index_divergences(
        bars,
        DivergenceConfig(pivot_window=1, compare_pivots=3, min_price_change_pct=0.001, indicator="rsi"),
    )

    assert any(point.kind == "底背离" and point.date == bars[7].date for point in points)


def test_detects_top_divergence_with_volume():
    bars = [
        bar(0, 10.0, high=10.0),
        bar(1, 10.5, high=10.5),
        bar(2, 11.0, high=11.0),
        bar(3, 10.6, high=10.6),
        bar(4, 10.2, high=10.2),
        bar(5, 10.8, high=10.8),
        bar(6, 11.3, high=11.3),
        bar(7, 10.7, high=10.7),
    ]
    bars = [
        DailyIndexBar(item.date, item.open, item.high, item.low, item.close, volume)
        for item, volume in zip(bars, [1000, 1200, 2000, 900, 800, 900, 1200, 700])
    ]

    points = detect_index_divergences(
        bars,
        DivergenceConfig(pivot_window=1, compare_pivots=3, min_price_change_pct=0.001, indicator="volume"),
    )

    assert any(point.kind == "顶背离" and point.date == bars[6].date for point in points)


def test_load_daily_index_with_chinese_columns(tmp_path):
    path = tmp_path / "index.csv"
    pd.DataFrame(
        [
            {"日期": "2024-01-02", "开盘": 3000, "最高": 3020, "最低": 2990, "收盘": 3010, "成交量": 100},
            {"日期": "2024-01-03", "开盘": 3010, "最高": 3030, "最低": 3000, "收盘": 3020, "成交量": 120},
        ]
    ).to_csv(path, index=False, encoding="utf-8-sig")

    bars = load_daily_index(path)

    assert len(bars) == 2
    assert bars[0].close == 3010
    assert bars[1].volume == 120
