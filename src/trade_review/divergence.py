from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from .io import float_or_zero, normalize_label, read_table


DAILY_INDEX_COLUMN_ALIASES = {
    "date": ["日期", "交易日期", "时间", "date", "trade_date"],
    "open": ["开盘", "开盘价", "open"],
    "high": ["最高", "最高价", "high"],
    "low": ["最低", "最低价", "low"],
    "close": ["收盘", "收盘价", "最新价", "close", "price"],
    "volume": ["成交量", "成交手数", "volume", "vol"],
    "amount": ["成交额", "金额", "amount"],
}


@dataclass(frozen=True)
class DailyIndexBar:
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    amount: float = 0.0


@dataclass(frozen=True)
class DivergencePoint:
    date: datetime
    kind: str
    price: float
    previous_date: datetime
    previous_price: float
    indicator_name: str
    indicator_value: float
    previous_indicator_value: float
    price_change_pct: float
    indicator_change_pct: float
    strength: str


@dataclass(frozen=True)
class DivergenceConfig:
    pivot_window: int = 2
    compare_pivots: int = 5
    min_price_change_pct: float = 0.003
    indicator_tolerance_pct: float = 0.001
    indicator: str = "macd"


def load_daily_index(path: str | Path) -> list[DailyIndexBar]:
    df = read_table(path)
    return dataframe_to_daily_bars(df)


def load_daily_index_from_akshare(
    symbol: str,
    start_date: str = "19700101",
    end_date: str = "22220101",
) -> list[DailyIndexBar]:
    try:
        import akshare as ak  # type: ignore
    except Exception as exc:
        raise RuntimeError("未安装 AKShare，无法自动读取指数日线；请改用 --index-daily 提供本地文件。") from exc

    df = ak.index_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date)
    return dataframe_to_daily_bars(df)


def dataframe_to_daily_bars(df: pd.DataFrame) -> list[DailyIndexBar]:
    mapping = resolve_daily_columns(df.columns)
    missing = [key for key in ["date", "close"] if key not in mapping]
    if missing:
        raise ValueError(f"指数日线文件缺少必要字段: {', '.join(missing)}")

    bars: list[DailyIndexBar] = []
    for _, row in df.iterrows():
        close = float_or_zero(row[mapping["close"]])
        if close <= 0:
            continue
        date = pd.to_datetime(row[mapping["date"]]).to_pydatetime()
        bars.append(
            DailyIndexBar(
                date=date,
                open=float_or_zero(row[mapping["open"]]) if "open" in mapping else close,
                high=float_or_zero(row[mapping["high"]]) if "high" in mapping else close,
                low=float_or_zero(row[mapping["low"]]) if "low" in mapping else close,
                close=close,
                volume=float_or_zero(row[mapping["volume"]]) if "volume" in mapping else 0.0,
                amount=float_or_zero(row[mapping["amount"]]) if "amount" in mapping else 0.0,
            )
        )
    return sorted(bars, key=lambda item: item.date)


def resolve_daily_columns(columns: Iterable[object]) -> dict[str, str]:
    normalized = {normalize_label(column): str(column) for column in columns}
    result: dict[str, str] = {}
    for key, aliases in DAILY_INDEX_COLUMN_ALIASES.items():
        for alias in aliases:
            label = normalize_label(alias)
            if label in normalized:
                result[key] = normalized[label]
                break
    return result


def detect_index_divergences(
    bars: list[DailyIndexBar],
    config: DivergenceConfig | None = None,
) -> list[DivergencePoint]:
    config = config or DivergenceConfig()
    if len(bars) < config.pivot_window * 2 + 3:
        return []

    indicator_name, indicator_values = build_indicator(bars, config.indicator)
    highs = pivot_indices([bar.high for bar in bars], config.pivot_window, "high")
    lows = pivot_indices([bar.low for bar in bars], config.pivot_window, "low")

    results: list[DivergencePoint] = []
    results.extend(
        compare_pivots(
            bars,
            indicator_values,
            indicator_name,
            highs,
            "顶背离",
            config,
        )
    )
    results.extend(
        compare_pivots(
            bars,
            indicator_values,
            indicator_name,
            lows,
            "底背离",
            config,
        )
    )
    return sorted(results, key=lambda item: item.date)


def build_indicator(bars: list[DailyIndexBar], indicator: str) -> tuple[str, list[float]]:
    closes = [bar.close for bar in bars]
    normalized = indicator.lower()
    if normalized == "dif":
        dif, _, _ = macd(closes)
        return "DIF", dif
    if normalized == "rsi":
        return "RSI(14)", rsi(closes, 14)
    if normalized == "volume":
        return "成交量", [bar.volume for bar in bars]
    dif, dea, hist = macd(closes)
    _ = dif, dea
    return "MACD柱", hist


def compare_pivots(
    bars: list[DailyIndexBar],
    indicator_values: list[float],
    indicator_name: str,
    pivots: list[int],
    kind: str,
    config: DivergenceConfig,
) -> list[DivergencePoint]:
    results: list[DivergencePoint] = []
    for position, current_idx in enumerate(pivots[1:], 1):
        previous_candidates = pivots[max(0, position - config.compare_pivots):position]
        current_price = bars[current_idx].high if kind == "顶背离" else bars[current_idx].low
        current_indicator = indicator_values[current_idx]
        for previous_idx in reversed(previous_candidates):
            previous_price = bars[previous_idx].high if kind == "顶背离" else bars[previous_idx].low
            previous_indicator = indicator_values[previous_idx]
            if previous_price <= 0:
                continue
            price_change = pct_change(previous_price, current_price)
            indicator_change = pct_change(abs(previous_indicator) or 1.0, abs(current_indicator))
            if is_divergence(kind, price_change, current_indicator, previous_indicator, config):
                results.append(
                    DivergencePoint(
                        date=bars[current_idx].date,
                        kind=kind,
                        price=current_price,
                        previous_date=bars[previous_idx].date,
                        previous_price=previous_price,
                        indicator_name=indicator_name,
                        indicator_value=current_indicator,
                        previous_indicator_value=previous_indicator,
                        price_change_pct=price_change,
                        indicator_change_pct=indicator_change,
                        strength=classify_strength(price_change, current_indicator, previous_indicator),
                    )
                )
                break
    return results


def is_divergence(
    kind: str,
    price_change: float,
    current_indicator: float,
    previous_indicator: float,
    config: DivergenceConfig,
) -> bool:
    tolerance = max(abs(previous_indicator) * config.indicator_tolerance_pct, 1e-9)
    if kind == "顶背离":
        return (
            price_change >= config.min_price_change_pct
            and current_indicator < previous_indicator - tolerance
        )
    return (
        price_change <= -config.min_price_change_pct
        and current_indicator > previous_indicator + tolerance
    )


def pivot_indices(values: list[float], window: int, mode: str) -> list[int]:
    indices: list[int] = []
    for idx in range(window, len(values) - window):
        current = values[idx]
        left = values[idx - window:idx]
        right = values[idx + 1:idx + window + 1]
        if mode == "high" and current >= max(left) and current >= max(right):
            indices.append(idx)
        elif mode == "low" and current <= min(left) and current <= min(right):
            indices.append(idx)
    return indices


def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[list[float], list[float], list[float]]:
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    dif = [fast_value - slow_value for fast_value, slow_value in zip(fast_ema, slow_ema)]
    dea = ema(dif, signal)
    hist = [(dif_value - dea_value) * 2 for dif_value, dea_value in zip(dif, dea)]
    return dif, dea, hist


def ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(value * alpha + result[-1] * (1 - alpha))
    return result


def rsi(closes: list[float], period: int) -> list[float]:
    if not closes:
        return []
    values = [50.0]
    avg_gain = 0.0
    avg_loss = 0.0
    for idx in range(1, len(closes)):
        change = closes[idx] - closes[idx - 1]
        gain = max(change, 0.0)
        loss = abs(min(change, 0.0))
        if idx <= period:
            avg_gain = (avg_gain * (idx - 1) + gain) / idx
            avg_loss = (avg_loss * (idx - 1) + loss) / idx
        else:
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            values.append(100 - 100 / (1 + rs))
    return values


def pct_change(start: float, end: float) -> float:
    if start == 0:
        return 0.0
    return (end - start) / start


def classify_strength(price_change: float, current_indicator: float, previous_indicator: float) -> str:
    indicator_gap = abs(current_indicator - previous_indicator) / max(abs(previous_indicator), 1.0)
    score = abs(price_change) + indicator_gap
    if score >= 0.08:
        return "强"
    if score >= 0.03:
        return "中"
    return "弱"


def render_divergence_markdown(
    divergences: list[DivergencePoint],
    index_name: str = "大盘指数",
) -> str:
    lines = [f"# {index_name}背离点分析", ""]
    if not divergences:
        lines.extend(["未识别到符合阈值的顶背离或底背离。", ""])
        return "\n".join(lines)

    top_count = sum(1 for item in divergences if item.kind == "顶背离")
    bottom_count = sum(1 for item in divergences if item.kind == "底背离")
    lines.extend(
        [
            "## 概览",
            "",
            f"- 背离点数量: {len(divergences)}",
            f"- 顶背离: {top_count}",
            f"- 底背离: {bottom_count}",
            "",
            "| 日期 | 类型 | 强度 | 指数点位 | 对比日期 | 对比点位 | 指标 | 指标变化 |",
            "| --- | --- | --- | ---: | --- | ---: | --- | ---: |",
        ]
    )
    for item in divergences:
        lines.append(
            "| "
            f"{item.date:%Y-%m-%d} | {item.kind} | {item.strength} | {item.price:.2f} | "
            f"{item.previous_date:%Y-%m-%d} | {item.previous_price:.2f} | "
            f"{item.indicator_name} {item.previous_indicator_value:.4f} -> {item.indicator_value:.4f} | "
            f"{item.indicator_change_pct * 100:.2f}% |"
        )
    lines.append("")
    return "\n".join(lines)


def write_divergence_markdown(
    divergences: list[DivergencePoint],
    output: str | Path,
    index_name: str = "大盘指数",
) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_divergence_markdown(divergences, index_name), encoding="utf-8")
    return output
