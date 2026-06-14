from datetime import date

import pandas as pd

from trade_review.sector_divergence import (
    DivergenceConfig,
    SectorDay,
    analyze_sector_divergence,
    load_sector_days,
    render_sector_report,
)


def test_load_sector_days_keeps_daily_top_three(tmp_path):
    path = tmp_path / "sectors.csv"
    pd.DataFrame(
        [
            {"日期": "2024-06-11", "板块": "A", "涨幅": 1.0},
            {"日期": "2024-06-11", "板块": "B", "涨幅": "5.0%"},
            {"日期": "2024-06-11", "板块": "C", "涨幅": 3.0},
            {"日期": "2024-06-11", "板块": "D", "涨幅": 2.0},
        ]
    ).to_csv(path, index=False, encoding="utf-8-sig")

    days = load_sector_days(path)

    assert [(item.rank, item.sector) for item in days] == [(1, "B"), (2, "C"), (3, "D")]
    assert days[0].pct == 5.0


def test_analyze_sector_divergence_detects_rotation_and_market_spread():
    days = [
        SectorDay(date(2024, 6, 11), "A", 5.0, 1, index_pct=1.0),
        SectorDay(date(2024, 6, 11), "B", 4.0, 2, index_pct=1.0),
        SectorDay(date(2024, 6, 11), "C", 3.0, 3, index_pct=1.0),
        SectorDay(date(2024, 6, 12), "D", 4.0, 1, index_pct=-0.5),
        SectorDay(date(2024, 6, 12), "E", 3.0, 2, index_pct=-0.5),
        SectorDay(date(2024, 6, 12), "C", 2.5, 3, index_pct=-0.5),
    ]

    signals = analyze_sector_divergence(days)
    kinds = {item.kind for item in signals}

    assert "热点强于大盘" in kinds
    assert "热点轮动" in kinds


def test_analyze_sector_divergence_detects_leader_weakening():
    days = [
        SectorDay(date(2024, 6, 10), "A", 6.0, 1, amount=100),
        SectorDay(date(2024, 6, 10), "B", 3.0, 2),
        SectorDay(date(2024, 6, 10), "C", 2.0, 3),
        SectorDay(date(2024, 6, 11), "A", 5.0, 1, amount=90),
        SectorDay(date(2024, 6, 11), "D", 3.0, 2),
        SectorDay(date(2024, 6, 11), "E", 2.0, 3),
        SectorDay(date(2024, 6, 12), "A", 4.0, 1, amount=80),
        SectorDay(date(2024, 6, 12), "F", 3.0, 2),
        SectorDay(date(2024, 6, 12), "G", 2.0, 3),
    ]

    signals = analyze_sector_divergence(days, DivergenceConfig(weakening_days=2))

    assert any(item.kind == "龙头走弱" and item.level == "高" for item in signals)


def test_render_sector_report_lists_signals():
    days = [SectorDay(date(2024, 6, 11), "A", 5.0, 1)]
    signals = analyze_sector_divergence(days)

    text = render_sector_report(days, signals)

    assert "# 板块背离分析报告" in text
    assert "A" in text
