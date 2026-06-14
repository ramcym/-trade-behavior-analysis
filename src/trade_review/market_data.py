from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .io import find_data_file, load_intraday
from .models import IntradayPoint, Trade


INDEX_BY_MARKET = {
    "60": "000001",
    "68": "000001",
    "00": "399001",
    "30": "399006",
}


@dataclass
class MarketBundle:
    index_code: str
    index_points: list[IntradayPoint]
    board_name: str
    board_points: list[IntradayPoint]
    stock_points: list[IntradayPoint]
    topic_status: str
    warnings: list[str]


class MarketDataProvider:
    def get_bundle(self, trade: Trade) -> MarketBundle:
        raise NotImplementedError


class LocalMarketDataProvider(MarketDataProvider):
    def __init__(self, ticks_dir: str | Path | None = None, market_dir: str | Path | None = None, board_map: dict[str, str] | None = None):
        self.ticks_dir = Path(ticks_dir) if ticks_dir else None
        self.market_dir = Path(market_dir) if market_dir else None
        self.board_map = board_map or {}

    def get_bundle(self, trade: Trade) -> MarketBundle:
        warnings: list[str] = []
        index_code = choose_index_code(trade.code)
        stock_points = self._load_stock_points(trade, warnings)
        index_points = self._load_index_points(trade, index_code, warnings)
        board_name = self.board_map.get(trade.code, "")
        board_points = self._load_board_points(trade, board_name, warnings)
        topic_status = "题材无法确认"
        if board_points and board_name:
            topic_status = f"热点/题材: {board_name}"
        elif board_points:
            topic_status = "板块数据可用但题材未命名"
        elif index_points:
            topic_status = "冷门题材或板块缺失，改用个股 vs 大盘"
        return MarketBundle(
            index_code=index_code,
            index_points=index_points,
            board_name=board_name,
            board_points=board_points,
            stock_points=stock_points,
            topic_status=topic_status,
            warnings=warnings,
        )

    def _load_stock_points(self, trade: Trade, warnings: list[str]) -> list[IntradayPoint]:
        path = find_data_file(self.ticks_dir, trade.code, trade.trade_dt)
        if not path:
            warnings.append("缺少个股逐笔/分时成交数据，无法识别点火单和承接。")
            return []
        return load_intraday(path, trade.trade_dt)

    def _load_index_points(self, trade: Trade, index_code: str, warnings: list[str]) -> list[IntradayPoint]:
        path = find_data_file(self.market_dir, index_code, trade.trade_dt, prefix="index")
        if not path:
            warnings.append(f"缺少大盘指数 {index_code} 分时数据。")
            return []
        return load_intraday(path, trade.trade_dt)

    def _load_board_points(self, trade: Trade, board_name: str, warnings: list[str]) -> list[IntradayPoint]:
        if not self.market_dir:
            warnings.append("缺少板块/题材分时数据。")
            return []
        date_text = trade.trade_dt.strftime("%Y%m%d")
        candidates = []
        for path in self.market_dir.glob("*"):
            if path.suffix.lower() not in {".csv", ".xlsx", ".xls"}:
                continue
            stem = path.stem
            if "board" not in stem or date_text not in stem:
                continue
            if board_name and board_name not in stem:
                continue
            candidates.append(path)
        if not candidates:
            warnings.append("缺少板块/题材分时数据。")
            return []
        return load_intraday(sorted(candidates)[0], trade.trade_dt)


class AkshareMarketDataProvider(LocalMarketDataProvider):
    """Optional AKShare provider with local-file fallback.

    The exact availability of historical 1-minute data changes by upstream source.
    Failures are converted to warnings so the review can still run on local exports.
    """

    def get_bundle(self, trade: Trade) -> MarketBundle:
        bundle = super().get_bundle(trade)
        try:
            import akshare as ak  # type: ignore
        except Exception:
            bundle.warnings.append("未安装 AKShare，已仅使用本地导出数据。")
            return bundle

        start = trade.trade_dt.strftime("%Y-%m-%d 09:30:00")
        end = trade.trade_dt.strftime("%Y-%m-%d 15:00:00")
        if not bundle.index_points:
            try:
                df = ak.index_zh_a_hist_min_em(symbol=bundle.index_code, period="1", start_date=start, end_date=end)
                bundle.index_points = dataframe_to_points(df, trade.trade_dt)
            except Exception as exc:
                bundle.warnings.append(f"AKShare 大盘分时获取失败: {exc}")
        return bundle


def choose_index_code(code: str) -> str:
    for prefix, index_code in INDEX_BY_MARKET.items():
        if code.startswith(prefix):
            return index_code
    return "000001"


def dataframe_to_points(df, default_date: datetime) -> list[IntradayPoint]:
    from .io import load_intraday

    temp = df.copy()
    return [
        IntradayPoint(ts=row.ts, price=row.price, volume=row.volume, amount=row.amount, side=row.side)
        for row in load_intraday_from_dataframe(temp, default_date)
    ]


def load_intraday_from_dataframe(df, default_date: datetime) -> list[IntradayPoint]:
    from .io import INTRADAY_COLUMN_ALIASES, parse_intraday_datetime, resolve_columns, float_or_zero

    mapping = resolve_columns(df.columns, INTRADAY_COLUMN_ALIASES)
    if "price" not in mapping and "收盘" in df.columns:
        mapping["price"] = "收盘"
    points: list[IntradayPoint] = []
    for _, row in df.iterrows():
        points.append(
            IntradayPoint(
                ts=parse_intraday_datetime(row, mapping, default_date),
                price=float_or_zero(row[mapping["price"]]),
                volume=float_or_zero(row[mapping["volume"]]) if "volume" in mapping else 0.0,
                amount=float_or_zero(row[mapping["amount"]]) if "amount" in mapping else 0.0,
                side=str(row[mapping["side"]]).strip() if "side" in mapping else "",
            )
        )
    return sorted(points, key=lambda item: item.ts)
