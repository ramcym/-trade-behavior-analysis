from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analyzer import AnalyzerConfig, TradeAnalyzer
from .divergence import (
    DivergenceConfig,
    detect_index_divergences,
    load_daily_index,
    load_daily_index_from_akshare,
    write_divergence_markdown,
)
from .io import load_trades
from .market_data import AkshareMarketDataProvider, LocalMarketDataProvider
from .report import write_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="交割单复盘与大盘指数背离分析工具")
    parser.add_argument("--trades", help="交割单 CSV/XLSX 路径")
    parser.add_argument("--ticks-dir", help="个股逐笔/分时成交导出目录")
    parser.add_argument("--market-dir", help="大盘/板块分时导出目录")
    parser.add_argument("--board-map", help='股票代码到题材/板块名称映射 JSON，例如 {"300750":"锂电池"}')
    parser.add_argument("--output", default="reports/review.md", help="交割单复盘 Markdown 输出路径")
    parser.add_argument("--use-akshare", action="store_true", help="尝试使用 AKShare 自动补齐大盘分时")
    parser.add_argument("--lookback-minutes", type=int, default=30, help="买入前分时分析窗口")

    parser.add_argument("--index-daily", help="大盘指数日线 CSV/XLSX 路径，用于识别顶/底背离")
    parser.add_argument("--index-code", help="通过 AKShare 自动读取指数日线，例如上证指数 000001、深证成指 399001")
    parser.add_argument("--index-start", default="19700101", help="AKShare 指数日线开始日期，格式 YYYYMMDD")
    parser.add_argument("--index-end", default="22220101", help="AKShare 指数日线结束日期，格式 YYYYMMDD")
    parser.add_argument("--index-name", default="大盘指数", help="指数名称，写入背离报告标题")
    parser.add_argument("--divergence-output", default="reports/index_divergence.md", help="指数背离报告输出路径")
    parser.add_argument(
        "--divergence-indicator",
        choices=["macd", "dif", "rsi", "volume"],
        default="macd",
        help="背离指标，默认 macd 表示 MACD 柱",
    )
    parser.add_argument("--pivot-window", type=int, default=2, help="局部高低点左右确认窗口")
    parser.add_argument("--divergence-compare-pivots", type=int, default=5, help="每个高低点向前对比的枢轴数量")
    parser.add_argument("--min-price-change-pct", type=float, default=0.003, help="判定新高/新低的最小幅度，例如 0.003 表示 0.3%")
    args = parser.parse_args(argv)

    if args.index_daily or args.index_code:
        if args.index_daily:
            bars = load_daily_index(args.index_daily)
        else:
            bars = load_daily_index_from_akshare(args.index_code, args.index_start, args.index_end)
        divergences = detect_index_divergences(
            bars,
            DivergenceConfig(
                pivot_window=args.pivot_window,
                compare_pivots=args.divergence_compare_pivots,
                min_price_change_pct=args.min_price_change_pct,
                indicator=args.divergence_indicator,
            ),
        )
        output = write_divergence_markdown(divergences, args.divergence_output, args.index_name)
        print(f"指数背离分析完成: {output}")
        if not args.trades:
            return 0

    if not args.trades:
        parser.error("请提供 --trades 做交割单复盘，或提供 --index-daily 做指数背离分析。")

    board_map = load_board_map(args.board_map)
    provider_cls = AkshareMarketDataProvider if args.use_akshare else LocalMarketDataProvider
    provider = provider_cls(ticks_dir=args.ticks_dir, market_dir=args.market_dir, board_map=board_map)
    analyzer = TradeAnalyzer(provider, AnalyzerConfig(lookback_minutes=args.lookback_minutes))
    trades = load_trades(args.trades)
    reviews = analyzer.review(trades)
    output = write_markdown(reviews, args.output)
    print(f"复盘完成: {output}")
    return 0


def load_board_map(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {str(key).zfill(6): str(value) for key, value in data.items()}


if __name__ == "__main__":
    raise SystemExit(main())
