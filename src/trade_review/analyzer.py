from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean

from .market_data import MarketBundle, MarketDataProvider
from .models import BuyPointType, IntradayPoint, ReviewConclusion, SignalEvidence, Trade, TradeReview


@dataclass(frozen=True)
class AnalyzerConfig:
    lookback_minutes: int = 30
    after_minutes: int = 10
    ignition_volume_multiplier: float = 2.0
    ignition_price_jump_pct: float = 0.003
    rebound_height_pct: float = 0.006
    near_low_tolerance_pct: float = 0.004
    anti_break_tolerance_pct: float = 0.002


class TradeAnalyzer:
    def __init__(self, provider: MarketDataProvider, config: AnalyzerConfig | None = None):
        self.provider = provider
        self.config = config or AnalyzerConfig()

    def review(self, trades: list[Trade]) -> list[TradeReview]:
        return [self.review_trade(trade) for trade in trades]

    def review_trade(self, trade: Trade) -> TradeReview:
        bundle = self.provider.get_bundle(trade)
        evidences: list[SignalEvidence] = []
        evidences.extend(self._market_evidence(trade, bundle))
        ignition = self._ignition_evidence(trade, bundle.stock_points)
        second = self._second_dip_evidence(trade, bundle)
        evidences.append(ignition)
        evidences.extend(second)

        buy_point_type = classify_buy_point(evidences)
        conclusion = conclude(evidences, buy_point_type)
        suggestion = make_suggestion(evidences, buy_point_type, bundle.warnings)
        for warning in bundle.warnings:
            evidences.append(SignalEvidence("数据提示", None, warning, 0))
        return TradeReview(
            trade=trade,
            buy_point_type=buy_point_type,
            conclusion=conclusion,
            evidences=evidences,
            suggestion=suggestion,
            topic_status=bundle.topic_status,
        )

    def _market_evidence(self, trade: Trade, bundle: MarketBundle) -> list[SignalEvidence]:
        results: list[SignalEvidence] = []
        index_trend = trend_before(bundle.index_points, trade.trade_dt, self.config.lookback_minutes)
        board_trend = trend_before(bundle.board_points, trade.trade_dt, self.config.lookback_minutes)
        stock_trend = trend_before(bundle.stock_points, trade.trade_dt, self.config.lookback_minutes)

        results.append(trend_to_evidence("大盘分时", index_trend, "大盘买入前分时"))
        if bundle.board_points:
            results.append(trend_to_evidence("板块/题材分时", board_trend, "题材买入前分时"))
        else:
            relative = compare_relative(stock_trend, index_trend)
            results.append(
                SignalEvidence(
                    "冷门题材处理",
                    None if relative is None else relative >= 0,
                    f"无可用板块分时，改看个股相对大盘；相对强度 {format_pct(relative)}。",
                    1 if relative is not None and relative >= 0 else 0,
                )
            )
        relative_board = compare_relative(stock_trend, board_trend if bundle.board_points else index_trend)
        results.append(
            SignalEvidence(
                "个股相对强度",
                None if relative_board is None else relative_board >= 0,
                f"个股买入前相对参照对象强度 {format_pct(relative_board)}。",
                1 if relative_board is not None and relative_board >= 0 else 0,
            )
        )
        return results

    def _ignition_evidence(self, trade: Trade, stock_points: list[IntradayPoint]) -> SignalEvidence:
        window = points_between(stock_points, trade.trade_dt - timedelta(minutes=5), trade.trade_dt)
        if len(window) < 3:
            return SignalEvidence("点火单确认", None, "买入前 5 分钟个股成交数据不足。", 0)
        volumes = [p.volume for p in window if p.volume > 0]
        avg_volume = mean(volumes[:-1]) if len(volumes) > 1 else 0.0
        last_volume = volumes[-1] if volumes else 0.0
        price_jump = pct_change(window[0].price, window[-1].price)
        active_buy_count = sum(1 for p in window[-5:] if is_active_buy(p.side))
        passed = (
            price_jump >= self.config.ignition_price_jump_pct
            and (avg_volume == 0 or last_volume >= avg_volume * self.config.ignition_volume_multiplier)
            and active_buy_count >= 1
        )
        detail = (
            f"买入前 5 分钟涨幅 {format_pct(price_jump)}，末段量能/均量 "
            f"{last_volume:.0f}/{avg_volume:.0f}，主动买标记 {active_buy_count} 条。"
        )
        return SignalEvidence("点火单确认", passed, detail, 2 if passed else 0)

    def _second_dip_evidence(self, trade: Trade, bundle: MarketBundle) -> list[SignalEvidence]:
        reference = bundle.board_points or bundle.index_points
        if len(reference) < 5 or len(bundle.stock_points) < 5:
            return [SignalEvidence("第二买点", None, "板块/大盘或个股分时数据不足，无法识别第二低点。", 0)]

        ref_pattern = detect_second_dip(reference, trade.trade_dt, self.config)
        stock_pattern = detect_second_dip(bundle.stock_points, trade.trade_dt, self.config)
        if not ref_pattern or not stock_pattern:
            return [SignalEvidence("第二买点", False, "买入前没有形成清晰的两低点结构。", 0)]

        ref_new_low = ref_pattern.second_low_price <= ref_pattern.first_low_price * (1 - self.config.anti_break_tolerance_pct)
        stock_holds_low = stock_pattern.second_low_price >= stock_pattern.first_low_price * (1 - self.config.anti_break_tolerance_pct)
        rebound_ok = stock_pattern.rebound_pct >= self.config.rebound_height_pct
        near_low = abs(pct_change(stock_pattern.second_low_price, trade.price)) <= self.config.near_low_tolerance_pct
        market_risk = is_sharp_falling(bundle.index_points, trade.trade_dt)

        return [
            SignalEvidence("板块二低结构", ref_new_low, f"参照对象第二低点相对前低 {format_pct(pct_change(ref_pattern.first_low_price, ref_pattern.second_low_price))}。", 1 if ref_new_low else 0),
            SignalEvidence("个股抗跌", stock_holds_low, f"个股第二低点相对前低 {format_pct(pct_change(stock_pattern.first_low_price, stock_pattern.second_low_price))}。", 2 if stock_holds_low else 0),
            SignalEvidence("反弹高度", rebound_ok, f"两个低点之间反弹高度 {format_pct(stock_pattern.rebound_pct)}。", 1 if rebound_ok else 0),
            SignalEvidence("低吸位置", near_low, f"买入价相对第二低点偏离 {format_pct(pct_change(stock_pattern.second_low_price, trade.price))}。", 1 if near_low else 0),
            SignalEvidence("大盘过滤", not market_risk, "大盘未出现买入前同步急跌。" if not market_risk else "大盘买入前同步急跌，第二买点降级为高风险低吸。", 1 if not market_risk else 0),
        ]


@dataclass(frozen=True)
class SecondDipPattern:
    first_low_time: datetime
    first_low_price: float
    rebound_high_time: datetime
    rebound_high_price: float
    second_low_time: datetime
    second_low_price: float
    rebound_pct: float


def detect_second_dip(points: list[IntradayPoint], trade_dt: datetime, config: AnalyzerConfig) -> SecondDipPattern | None:
    window = points_between(points, trade_dt - timedelta(minutes=config.lookback_minutes), trade_dt + timedelta(minutes=2))
    if len(window) < 5:
        return None
    trade_index = max((idx for idx, p in enumerate(window) if p.ts <= trade_dt), default=len(window) - 1)
    before_trade = window[: trade_index + 1]
    if len(before_trade) < 5:
        return None

    # The second dip should be the low near the planned entry, not the first
    # low of the whole lookback window.
    low_indices = local_low_indices(before_trade)
    if len(low_indices) < 2:
        return None
    second_idx = low_indices[-1]
    first_idx = low_indices[-2]
    if first_idx >= second_idx - 1:
        return None
    first_low = before_trade[first_idx]
    second_low = before_trade[second_idx]
    rebound_slice = before_trade[first_idx: second_idx + 1]
    rebound_high = max(rebound_slice, key=lambda p: p.price)
    rebound_pct = pct_change(first_low.price, rebound_high.price)
    return SecondDipPattern(
        first_low_time=first_low.ts,
        first_low_price=first_low.price,
        rebound_high_time=rebound_high.ts,
        rebound_high_price=rebound_high.price,
        second_low_time=second_low.ts,
        second_low_price=second_low.price,
        rebound_pct=rebound_pct,
    )


def local_low_indices(points: list[IntradayPoint]) -> list[int]:
    lows: list[int] = []
    for idx, point in enumerate(points):
        previous_price = points[idx - 1].price if idx > 0 else float("inf")
        next_price = points[idx + 1].price if idx + 1 < len(points) else float("inf")
        if point.price <= previous_price and point.price <= next_price:
            lows.append(idx)
    return lows


def trend_before(points: list[IntradayPoint], trade_dt: datetime, minutes: int) -> float | None:
    window = points_between(points, trade_dt - timedelta(minutes=minutes), trade_dt)
    if len(window) < 2:
        return None
    return pct_change(window[0].price, window[-1].price)


def points_between(points: list[IntradayPoint], start: datetime, end: datetime) -> list[IntradayPoint]:
    return [p for p in points if start <= p.ts <= end and p.price > 0]


def pct_change(start: float, end: float) -> float:
    if start == 0:
        return 0.0
    return (end - start) / start


def compare_relative(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def trend_to_evidence(name: str, value: float | None, prefix: str) -> SignalEvidence:
    if value is None:
        return SignalEvidence(name, None, f"{prefix}数据不足。", 0)
    passed = value >= 0
    return SignalEvidence(name, passed, f"{prefix}涨跌幅 {format_pct(value)}。", 1 if passed else 0)


def classify_buy_point(evidences: list[SignalEvidence]) -> BuyPointType:
    evidence_by_name = {item.name: item for item in evidences}
    ignition = evidence_by_name.get("点火单确认")
    market = evidence_by_name.get("大盘分时")
    relative = evidence_by_name.get("个股相对强度")
    second_names = ["板块二低结构", "个股抗跌", "反弹高度", "低吸位置"]
    second_score = sum(1 for name in second_names if evidence_by_name.get(name) and evidence_by_name[name].passed)
    if second_score >= 3:
        return BuyPointType.SECOND_DIP
    if ignition and ignition.passed and market and market.passed and relative and relative.passed:
        return BuyPointType.IGNITION
    if any(item.passed is not None for item in evidences):
        return BuyPointType.OTHER
    return BuyPointType.UNKNOWN


def conclude(evidences: list[SignalEvidence], buy_point_type: BuyPointType) -> ReviewConclusion:
    judged = [item for item in evidences if item.passed is not None and item.name != "数据提示"]
    if not judged:
        return ReviewConclusion.UNKNOWN
    evidence_by_name = {item.name: item for item in evidences}
    if buy_point_type == BuyPointType.SECOND_DIP:
        names = ["板块二低结构", "个股抗跌", "反弹高度", "低吸位置", "大盘过滤"]
        passed_count = sum(1 for name in names if evidence_by_name.get(name) and evidence_by_name[name].passed)
        if passed_count >= 5:
            return ReviewConclusion.MATCH
        if passed_count >= 3:
            return ReviewConclusion.PARTIAL
        return ReviewConclusion.MISMATCH
    if buy_point_type == BuyPointType.IGNITION:
        names = ["大盘分时", "板块/题材分时", "冷门题材处理", "个股相对强度", "点火单确认"]
        available = [evidence_by_name[name] for name in names if name in evidence_by_name]
        passed_count = sum(1 for item in available if item.passed)
        if passed_count >= 4:
            return ReviewConclusion.MATCH
        if passed_count >= 2:
            return ReviewConclusion.PARTIAL
        return ReviewConclusion.MISMATCH
    passed = sum(item.score for item in evidences if item.passed)
    if buy_point_type in {BuyPointType.IGNITION, BuyPointType.SECOND_DIP} and passed >= 5 and failed <= 1:
        return ReviewConclusion.MATCH
    if passed >= 2:
        return ReviewConclusion.PARTIAL
    return ReviewConclusion.MISMATCH


def make_suggestion(evidences: list[SignalEvidence], buy_point_type: BuyPointType, warnings: list[str]) -> str:
    if warnings:
        return "先补齐缺失分时/逐笔数据，再复核买点证据；当前不宜判定为符合或不符合。"
    failed = [item.name for item in evidences if item.passed is False]
    if buy_point_type == BuyPointType.SECOND_DIP and "低吸位置" in failed:
        return "第二买点要贴近二低或拐头初期，反弹拉开后不再按低吸处理。"
    if buy_point_type == BuyPointType.IGNITION and "点火单确认" in failed:
        return "第一买点应等主动买单和量价推进同时出现后再介入。"
    if "个股相对强度" in failed:
        return "优先选择强于题材/大盘的个股，弱跟随不作为核心买点。"
    if "大盘过滤" in failed:
        return "大盘急跌时第二买点降级处理，仓位和确认条件都要更严格。"
    return "该笔交易证据较完整，后续重点复盘卖点和持仓执行。"


def is_active_buy(side: str) -> bool:
    lowered = side.lower()
    return any(token in side for token in ["买", "B", "主动买", "外盘"]) or lowered in {"buy", "b"}


def is_sharp_falling(points: list[IntradayPoint], trade_dt: datetime) -> bool:
    value = trend_before(points, trade_dt, 5)
    return value is not None and value <= -0.005


def format_pct(value: float | None) -> str:
    if value is None:
        return "无法计算"
    return f"{value * 100:.2f}%"
