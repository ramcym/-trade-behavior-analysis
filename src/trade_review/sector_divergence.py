from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from .io import float_or_zero, read_table, resolve_columns


SECTOR_COLUMN_ALIASES = {
    "date": ["日期", "交易日期", "date", "trade_date"],
    "sector": ["板块", "板块名称", "名称", "行业", "行业名称", "概念", "概念名称", "name", "sector"],
    "pct": ["涨幅", "涨跌幅", "涨跌幅%", "涨跌幅(%)", "pct", "change_pct", "pct_chg"],
    "rank": ["排名", "名次", "rank"],
    "amount": ["成交额", "成交金额", "amount", "turnover"],
    "volume": ["成交量", "volume"],
    "index_pct": ["大盘涨幅", "指数涨幅", "上证涨幅", "market_pct", "index_pct"],
}


@dataclass(frozen=True)
class DivergenceConfig:
    top_n: int = 3
    market_spread_pct: float = 2.5
    leader_spread_pct: float = 3.0
    weakening_days: int = 2
    min_hot_pct: float = 1.0


@dataclass(frozen=True)
class SectorDay:
    trade_date: date
    sector: str
    pct: float
    rank: int
    amount: float = 0.0
    volume: float = 0.0
    index_pct: float | None = None


@dataclass
class DivergenceSignal:
    trade_date: date
    kind: str
    level: str
    detail: str
    sectors: list[str] = field(default_factory=list)


def parse_pct_value(value: object) -> float:
    text = str(value).replace(",", "").strip()
    if text.endswith("%"):
        text = text[:-1]
    return float_or_zero(text)


def load_sector_days(path: str | Path, top_n: int = 3) -> list[SectorDay]:
    df = read_table(path)
    mapping = resolve_columns(df.columns, SECTOR_COLUMN_ALIASES)
    missing = [key for key in ["date", "sector", "pct"] if key not in mapping]
    if missing:
        raise ValueError(f"板块历史数据缺少必要字段: {', '.join(missing)}")

    working = df.copy()
    working["_trade_date"] = pd.to_datetime(working[mapping["date"]]).dt.date
    working["_sector"] = working[mapping["sector"]].astype(str).str.strip()
    working["_pct"] = working[mapping["pct"]].map(parse_pct_value)
    if "rank" in mapping:
        working["_rank"] = working[mapping["rank"]].map(lambda value: int(float_or_zero(value)) if float_or_zero(value) else 0)
    else:
        working["_rank"] = working.groupby("_trade_date")["_pct"].rank(method="first", ascending=False).astype(int)

    top = working[working["_rank"].between(1, top_n)].copy()
    if top.empty:
        top = (
            working.sort_values(["_trade_date", "_pct"], ascending=[True, False])
            .groupby("_trade_date")
            .head(top_n)
            .copy()
        )
        top["_rank"] = top.groupby("_trade_date")["_pct"].rank(method="first", ascending=False).astype(int)

    days: list[SectorDay] = []
    for _, row in top.sort_values(["_trade_date", "_rank"]).iterrows():
        index_pct = parse_pct_value(row[mapping["index_pct"]]) if "index_pct" in mapping else None
        days.append(
            SectorDay(
                trade_date=row["_trade_date"],
                sector=row["_sector"],
                pct=float(row["_pct"]),
                rank=int(row["_rank"]),
                amount=float_or_zero(row[mapping["amount"]]) if "amount" in mapping else 0.0,
                volume=float_or_zero(row[mapping["volume"]]) if "volume" in mapping else 0.0,
                index_pct=index_pct,
            )
        )
    return days


def analyze_sector_divergence(days: list[SectorDay], config: DivergenceConfig | None = None) -> list[DivergenceSignal]:
    config = config or DivergenceConfig()
    by_date: dict[date, list[SectorDay]] = {}
    for item in days:
        by_date.setdefault(item.trade_date, []).append(item)

    signals: list[DivergenceSignal] = []
    previous_top: list[SectorDay] = []
    history_by_sector: dict[str, list[SectorDay]] = {}

    for trade_date in sorted(by_date):
        top = sorted(by_date[trade_date], key=lambda item: item.rank)[: config.top_n]
        if not top:
            continue
        for item in top:
            history_by_sector.setdefault(item.sector, []).append(item)

        signals.extend(_market_divergence(trade_date, top, config))
        signals.extend(_leader_divergence(trade_date, top, history_by_sector, config))
        signals.extend(_rotation_divergence(trade_date, top, previous_top, config))
        signals.extend(_breadth_divergence(trade_date, top, config))
        previous_top = top

    return signals


def _market_divergence(trade_date: date, top: list[SectorDay], config: DivergenceConfig) -> list[DivergenceSignal]:
    market_values = [item.index_pct for item in top if item.index_pct is not None]
    if not market_values:
        return []
    index_pct = market_values[0]
    avg_top = sum(item.pct for item in top) / len(top)
    spread = avg_top - index_pct
    if index_pct <= 0 and avg_top >= config.min_hot_pct and spread >= config.market_spread_pct:
        return [
            DivergenceSignal(
                trade_date,
                "热点强于大盘",
                "中",
                f"前三板块均值 {avg_top:.2f}%，大盘 {index_pct:.2f}%，热点相对大盘强 {spread:.2f} 个百分点。",
                [item.sector for item in top],
            )
        ]
    if index_pct > 0 and spread >= config.market_spread_pct * 1.5:
        return [
            DivergenceSignal(
                trade_date,
                "局部过热",
                "中",
                f"大盘上涨 {index_pct:.2f}%，但前三板块均值 {avg_top:.2f}%，领先过大，需防次日分化。",
                [item.sector for item in top],
            )
        ]
    return []


def _leader_divergence(
    trade_date: date,
    top: list[SectorDay],
    history_by_sector: dict[str, list[SectorDay]],
    config: DivergenceConfig,
) -> list[DivergenceSignal]:
    leader = top[0]
    history = history_by_sector.get(leader.sector, [])
    if len(history) < config.weakening_days + 1:
        return []

    recent = history[-(config.weakening_days + 1) :]
    pct_weakening = all(recent[idx].pct < recent[idx - 1].pct for idx in range(1, len(recent)))
    amount_weakening = (
        all(item.amount > 0 for item in recent)
        and all(recent[idx].amount < recent[idx - 1].amount for idx in range(1, len(recent)))
    )
    if pct_weakening and amount_weakening:
        detail = f"{leader.sector} 连续 {len(recent)} 次进入前三，但涨幅和成交额同步递减。"
    elif pct_weakening:
        detail = f"{leader.sector} 连续 {len(recent)} 次进入前三，但涨幅逐次递减。"
    else:
        return []
    return [DivergenceSignal(trade_date, "龙头走弱", "高" if amount_weakening else "中", detail, [leader.sector])]


def _rotation_divergence(
    trade_date: date,
    top: list[SectorDay],
    previous_top: list[SectorDay],
    config: DivergenceConfig,
) -> list[DivergenceSignal]:
    if not previous_top:
        return []
    current_names = {item.sector for item in top}
    previous_names = {item.sector for item in previous_top}
    overlap = current_names & previous_names
    previous_leader = previous_top[0].sector
    if len(overlap) <= 1 and previous_leader not in current_names:
        return [
            DivergenceSignal(
                trade_date,
                "热点轮动",
                "中",
                f"前三板块仅延续 {len(overlap)} 个，前一日龙头 {previous_leader} 跌出前三，资金方向出现切换。",
                [item.sector for item in top],
            )
        ]
    return []


def _breadth_divergence(trade_date: date, top: list[SectorDay], config: DivergenceConfig) -> list[DivergenceSignal]:
    if len(top) < 2:
        return []
    rest_avg = sum(item.pct for item in top[1:]) / (len(top) - 1)
    spread = top[0].pct - rest_avg
    if spread >= config.leader_spread_pct:
        return [
            DivergenceSignal(
                trade_date,
                "前三内部背离",
                "中",
                f"第一名 {top[0].sector} 涨幅 {top[0].pct:.2f}%，领先第二/第三均值 {spread:.2f} 个百分点，强度集中。",
                [item.sector for item in top],
            )
        ]
    return []


def render_sector_report(days: list[SectorDay], signals: list[DivergenceSignal]) -> str:
    by_date: dict[date, list[SectorDay]] = {}
    for item in days:
        by_date.setdefault(item.trade_date, []).append(item)

    lines = ["# 板块背离分析报告", ""]
    lines.extend(["## 每日涨幅前三", "", "| 日期 | 排名 | 板块 | 涨幅 | 大盘涨幅 | 成交额 |", "| --- | ---: | --- | ---: | ---: | ---: |"])
    for trade_date in sorted(by_date):
        for item in sorted(by_date[trade_date], key=lambda value: value.rank):
            market = "" if item.index_pct is None else f"{item.index_pct:.2f}%"
            amount = "" if item.amount == 0 else f"{item.amount:.0f}"
            lines.append(f"| {trade_date:%Y-%m-%d} | {item.rank} | {item.sector} | {item.pct:.2f}% | {market} | {amount} |")

    lines.extend(["", "## 背离点", ""])
    if not signals:
        lines.append("未发现明显板块背离点。")
    else:
        lines.extend(["| 日期 | 类型 | 级别 | 涉及板块 | 说明 |", "| --- | --- | --- | --- | --- |"])
        for signal in signals:
            lines.append(
                f"| {signal.trade_date:%Y-%m-%d} | {signal.kind} | {signal.level} | {', '.join(signal.sectors)} | {signal.detail} |"
            )
    lines.append("")
    return "\n".join(lines)


def write_sector_report(days: list[SectorDay], signals: list[DivergenceSignal], output: str | Path) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_sector_report(days, signals), encoding="utf-8")
    return output


def fetch_akshare_sector_days(start_date: str, end_date: str, top_n: int = 3) -> list[SectorDay]:
    try:
        import akshare as ak  # type: ignore
    except Exception as exc:
        raise RuntimeError("未安装 AKShare，无法自动抓取历史板块排行。请先安装 akshare，或用 --input 提供本地文件。") from exc

    try:
        names_df = ak.stock_board_industry_name_em()
    except Exception as exc:
        raise RuntimeError(f"AKShare 获取板块列表失败: {exc}") from exc
    name_mapping = resolve_columns(names_df.columns, SECTOR_COLUMN_ALIASES)
    if "sector" not in name_mapping:
        raise RuntimeError("AKShare 板块列表字段无法识别，建议导出为本地文件后用 --input 分析。")

    start_text = pd.to_datetime(start_date).strftime("%Y%m%d")
    end_text = pd.to_datetime(end_date).strftime("%Y%m%d")
    rows: list[dict[str, object]] = []
    for sector in names_df[name_mapping["sector"]].dropna().astype(str).str.strip().unique():
        try:
            hist = ak.stock_board_industry_hist_em(symbol=sector, start_date=start_text, end_date=end_text, period="日k", adjust="")
        except Exception:
            continue
        mapping = resolve_columns(hist.columns, SECTOR_COLUMN_ALIASES)
        if "date" not in mapping or "pct" not in mapping:
            continue
        for _, row in hist.iterrows():
            rows.append(
                {
                    "日期": row[mapping["date"]],
                    "板块": sector,
                    "涨幅": row[mapping["pct"]],
                    "成交额": row[mapping["amount"]] if "amount" in mapping else 0,
                }
            )

    if not rows:
        raise RuntimeError("AKShare 未返回可用的历史板块日线数据，建议用 --input 提供本地 CSV/XLSX。")
    temp = pd.DataFrame(rows)
    temp["_trade_date"] = pd.to_datetime(temp["日期"]).dt.date
    temp["_sector"] = temp["板块"].astype(str).str.strip()
    temp["_pct"] = temp["涨幅"].map(parse_pct_value)
    temp["_amount"] = temp["成交额"].map(float_or_zero)
    temp["_rank"] = temp.groupby("_trade_date")["_pct"].rank(method="first", ascending=False).astype(int)
    top = temp[temp["_rank"].between(1, top_n)].sort_values(["_trade_date", "_rank"])
    return [
        SectorDay(
            trade_date=row["_trade_date"],
            sector=row["_sector"],
            pct=float(row["_pct"]),
            rank=int(row["_rank"]),
            amount=float(row["_amount"]),
        )
        for _, row in top.iterrows()
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="读取历史每日涨幅前三板块并分析板块背离点")
    parser.add_argument("--input", help="本地 CSV/XLSX 板块历史数据。可包含全板块，也可只包含每日前三。")
    parser.add_argument("--start-date", help="AKShare 抓取开始日期，格式 YYYY-MM-DD")
    parser.add_argument("--end-date", help="AKShare 抓取结束日期，格式 YYYY-MM-DD")
    parser.add_argument("--top-n", type=int, default=3, help="每日取涨幅前 N 名，默认 3")
    parser.add_argument("--output", default="reports/sector_divergence.md", help="输出 Markdown 报告路径")
    args = parser.parse_args(argv)

    config = DivergenceConfig(top_n=args.top_n)
    if args.input:
        days = load_sector_days(args.input, top_n=args.top_n)
    elif args.start_date and args.end_date:
        days = fetch_akshare_sector_days(args.start_date, args.end_date, top_n=args.top_n)
    else:
        parser.error("请提供 --input，或同时提供 --start-date 和 --end-date")

    signals = analyze_sector_divergence(days, config)
    output = write_sector_report(days, signals, args.output)
    print(f"板块背离分析完成: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
