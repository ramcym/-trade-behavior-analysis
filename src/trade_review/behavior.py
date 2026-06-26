from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .io import float_or_zero, normalize_code, parse_trade_datetime, read_table


SYSTEM_FITS = ["完全符合", "基本符合", "部分符合", "完全不符合", "未标注"]
PLAN_FOLLOWS = ["完全执行", "轻微变形", "明显变形", "完全情绪化", "未标注"]
EMOTIONS = ["冷静", "耐心", "兴奋", "FOMO", "焦虑", "急于修复", "赌一把", "未标注"]
EMOTION_SOURCES = ["连续盈利", "大赚后", "连续亏损", "想翻本", "怕踏空", "消息刺激", "群体影响"]
BUY_QUALITIES = ["计划买点", "提前买", "追高买", "翘板买", "补救买", "随手买", "未标注"]
POSITION_QUALITIES = ["合理", "偏重", "过重", "连续盈利后放大", "亏损后加仓", "未标注"]
STOP_EXECUTIONS = ["严格执行", "延迟执行", "没有执行", "不适用", "未标注"]
TRADE_TYPES = ["CORE_LEADER", "MID_CORE", "FOLLOWER", "EMOTION_TRADE", "UNMARKED"]
ENTRY_MODELS = ["IGNITION", "DIVERGENCE", "CHASE_HIGH", "RANDOM", "UNMARKED"]
MARKET_CONDITIONS = ["INDEX_UP", "INDEX_DOWN", "INDEX_FLAT", "UNMARKED"]
SECTOR_CONDITIONS = ["SECTOR_STRONG", "SECTOR_WEAK", "SECTOR_DIVERGE", "UNMARKED"]
STOCK_POSITIONS = ["FIRST_CHOICE", "SECOND_CHOICE", "NOT_CORE", "UNMARKED"]
SIGNAL_QUALITIES = ["FULL_CONFIRM", "MISSING_ONE", "MISSING_MULTI", "UNMARKED"]
EXIT_REASONS = [
    "STOP_LOSS",
    "TAKE_PROFIT",
    "SECTOR_DIVERGENCE",
    "STOCK_DIVERGENCE",
    "INDEX_WEAKNESS",
    "RULE_VIOLATION",
    "UNMARKED",
]
AVOIDABLE_LOSSES = ["YES", "NO", "UNMARKED"]
AVOIDABLE_REASONS = [
    "非核心杂毛",
    "连续盈利后降低标准",
    "顶背离追点火",
    "第一选择没买，买了第二选择",
    "大盘不配合",
    "板块不配合",
    "没有及时止损",
    "情绪化想赚回来",
]
ERROR_CODES = {
    "E01": "杂毛交易",
    "E02": "连续盈利后降低标准",
    "E03": "顶背离追点火",
    "E04": "第一选择没买，买第二选择",
    "E05": "大盘不配合仍买入",
    "E06": "板块不配合仍买入",
    "E07": "指数回流预期覆盖个股负面信号",
    "E08": "亏损后不止损，幻想修复",
    "E09": "把杂毛当龙头格局",
    "E10": "系统A买入，系统B卖出，买卖逻辑混乱",
}

SYSTEM_IN = {"完全符合", "基本符合"}
SYSTEM_OUT = {"完全不符合"}
EMOTION_RISK = {"兴奋", "FOMO", "焦虑", "急于修复", "赌一把"}
BAD_BUY_QUALITY = {"提前买", "追高买", "翘板买", "补救买", "随手买"}
BAD_POSITION = {"偏重", "过重", "连续盈利后放大", "亏损后加仓"}


@dataclass
class RawTradeRow:
    dt: datetime
    code: str
    name: str
    side: str
    quantity: float
    price: float
    amount: float
    fee: float


@dataclass
class ClosedTrade:
    trade_id: str
    code: str
    name: str
    buy_time: str
    sell_time: str
    quantity: float
    buy_price: float
    sell_price: float
    buy_amount: float
    pnl: float
    return_pct: float
    holding_hours: float
    buy_time_bucket: str
    rank_tag: str = ""
    win_streak_before: int = 0
    loss_streak_before: int = 0


@dataclass
class TradeAnnotation:
    trade_id: str
    system_fit: str = "未标注"
    plan_follow: str = "未标注"
    emotion_state: str = "未标注"
    emotion_sources: list[str] = field(default_factory=list)
    buy_quality: str = "未标注"
    position_quality: str = "未标注"
    stop_execution: str = "未标注"
    trade_type: str = "UNMARKED"
    entry_model: str = "UNMARKED"
    market_condition: str = "UNMARKED"
    sector_condition: str = "UNMARKED"
    stock_position: str = "UNMARKED"
    signal_quality: str = "UNMARKED"
    exit_reason: str = "UNMARKED"
    avoidable_loss: str = "UNMARKED"
    avoidable_reason: str = ""
    error_codes: list[str] = field(default_factory=list)
    plan_follow_score: int | None = None
    notes: str = ""


@dataclass
class BehaviorDiagnosis:
    trades: list[dict[str, Any]]
    annotations: dict[str, dict[str, Any]]
    summary: dict[str, Any]
    groups: dict[str, dict[str, Any]]
    simulations: dict[str, Any]
    emotion: dict[str, Any]
    risk_model: dict[str, Any]
    progress: list[dict[str, Any]]
    weekly_progress: list[dict[str, Any]]
    attribution: dict[str, Any]
    conclusions: list[str]


def load_closed_trades(trades_path: str | Path) -> list[ClosedTrade]:
    rows = load_raw_trade_rows(trades_path)
    positions: dict[str, list[dict[str, Any]]] = {}
    closed: list[ClosedTrade] = []

    for row in sorted(rows, key=lambda item: item.dt):
        if row.side == "buy":
            unit_cost = (row.amount + row.fee) / row.quantity if row.quantity else row.price
            positions.setdefault(row.code, []).append(
                {
                    **asdict(row),
                    "remain": row.quantity,
                    "unit_cost": unit_cost,
                }
            )
            continue

        remain = row.quantity
        sell_unit = (row.amount - row.fee) / row.quantity if row.quantity else row.price
        lots = positions.setdefault(row.code, [])
        while remain > 0 and lots:
            lot = lots[0]
            matched = min(remain, lot["remain"])
            pnl = (sell_unit - lot["unit_cost"]) * matched
            buy_amount = lot["amount"] * (matched / lot["quantity"]) if lot["quantity"] else 0.0
            return_pct = sell_unit / lot["unit_cost"] - 1 if lot["unit_cost"] else 0.0
            buy_dt = lot["dt"]
            closed.append(
                ClosedTrade(
                    trade_id="",
                    code=row.code,
                    name=row.name or lot["name"],
                    buy_time=buy_dt.isoformat(sep=" "),
                    sell_time=row.dt.isoformat(sep=" "),
                    quantity=matched,
                    buy_price=lot["price"],
                    sell_price=row.price,
                    buy_amount=buy_amount,
                    pnl=pnl,
                    return_pct=return_pct,
                    holding_hours=(row.dt - buy_dt).total_seconds() / 3600,
                    buy_time_bucket=time_bucket(buy_dt),
                )
            )
            lot["remain"] -= matched
            remain -= matched
            if lot["remain"] <= 0:
                lots.pop(0)

    closed = sorted(closed, key=lambda item: item.sell_time)
    assign_trade_metadata(closed)
    return closed


def load_raw_trade_rows(trades_path: str | Path) -> list[RawTradeRow]:
    df = read_table(trades_path)
    rows: list[RawTradeRow] = []
    for _, row in df.iterrows():
        try:
            dt = parse_trade_datetime(field(row, ["成交日期", "交易日期", "日期"], 0), field(row, ["成交时间", "交易时间", "时间"], 1))
            code = normalize_code(field(row, ["证券代码", "股票代码", "代码"], 2))
            name = str(field(row, ["证券名称", "股票名称", "名称"], 3))
            side_text = str(field(row, ["操作", "买卖方向", "业务名称"], 4))
            quantity = float_or_zero(field(row, ["成交数量", "成交股数", "数量"], 5))
            price = float_or_zero(field(row, ["成交均价", "成交价格", "成交价", "价格"], 7))
            amount = float_or_zero(field(row, ["成交金额", "金额"], 8))
            net_amount = float_or_zero(field(row, ["发生金额", "本次金额"], 11))
            fee = sum(
                float_or_zero(field(row, [name], fallback_idx, default=0))
                for name, fallback_idx in [("手续费", 12), ("印花税", 13), ("其他杂费", 14)]
            )
        except Exception as exc:
            raise ValueError("交割单格式暂不支持，请确认前 15 列是券商标准导出。") from exc
        if "买" in side_text and "卖" not in side_text:
            side = "buy"
        elif "卖" in side_text:
            side = "sell"
        else:
            side = "buy" if net_amount < 0 else "sell"
        rows.append(
            RawTradeRow(
                dt=dt,
                code=code,
                name=name,
                side=side,
                quantity=quantity,
                price=price,
                amount=amount,
                fee=fee,
            )
        )
    return rows


def field(row: Any, names: list[str], fallback_idx: int, default: Any | None = None) -> Any:
    normalized = {str(column).strip().lower().replace(" ", ""): column for column in row.index}
    for name in names:
        key = name.strip().lower().replace(" ", "")
        if key in normalized:
            return row[normalized[key]]
    if fallback_idx < len(row):
        return row.iloc[fallback_idx]
    return default


def assign_trade_metadata(trades: list[ClosedTrade]) -> None:
    win_streak = 0
    loss_streak = 0
    for idx, trade in enumerate(trades, 1):
        trade.trade_id = f"T{idx:04d}_{trade.code}_{trade.buy_time[:10].replace('-', '')}_{trade.sell_time[:10].replace('-', '')}"
        trade.win_streak_before = win_streak
        trade.loss_streak_before = loss_streak
        if trade.pnl > 0:
            win_streak += 1
            loss_streak = 0
        elif trade.pnl < 0:
            loss_streak += 1
            win_streak = 0
        else:
            win_streak = 0
            loss_streak = 0

    winners = sorted((t for t in trades if t.pnl > 0), key=lambda item: item.pnl, reverse=True)
    losers = sorted((t for t in trades if t.pnl < 0), key=lambda item: item.pnl)
    for trade in winners[:20]:
        if trade.return_pct >= 0.03 or winners.index(trade) < 20:
            trade.rank_tag = append_tag(trade.rank_tag, "大肉")
    for trade in losers[:20]:
        if trade.return_pct <= -0.03 or losers.index(trade) < 20:
            trade.rank_tag = append_tag(trade.rank_tag, "大亏")


def append_tag(existing: str, tag: str) -> str:
    tags = [item for item in existing.split(",") if item]
    if tag not in tags:
        tags.append(tag)
    return ",".join(tags)


def time_bucket(dt: datetime) -> str:
    minutes = dt.hour * 60 + dt.minute
    if minutes < 10 * 60:
        return "10点前"
    if minutes < 11 * 60 + 30:
        return "10:00-11:30"
    return "午后/临近午盘"


def load_annotations(path: str | Path) -> dict[str, TradeAnnotation]:
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        items = data
    else:
        items = data.get("annotations", [])
    annotations: dict[str, TradeAnnotation] = {}
    for item in items:
        annotation = TradeAnnotation(
            trade_id=str(item.get("trade_id", "")),
            system_fit=str(item.get("system_fit", "未标注")),
            plan_follow=str(item.get("plan_follow", "未标注")),
            emotion_state=str(item.get("emotion_state", "未标注")),
            emotion_sources=list(item.get("emotion_sources", [])),
            buy_quality=str(item.get("buy_quality", "未标注")),
            position_quality=str(item.get("position_quality", "未标注")),
            stop_execution=str(item.get("stop_execution", "未标注")),
            trade_type=str(item.get("trade_type", "UNMARKED")),
            entry_model=str(item.get("entry_model", "UNMARKED")),
            market_condition=str(item.get("market_condition", "UNMARKED")),
            sector_condition=str(item.get("sector_condition", "UNMARKED")),
            stock_position=str(item.get("stock_position", "UNMARKED")),
            signal_quality=str(item.get("signal_quality", "UNMARKED")),
            exit_reason=str(item.get("exit_reason", "UNMARKED")),
            avoidable_loss=str(item.get("avoidable_loss", "UNMARKED")),
            avoidable_reason=str(item.get("avoidable_reason", "")),
            error_codes=list(item.get("error_codes", [])),
            plan_follow_score=item.get("plan_follow_score"),
            notes=str(item.get("notes", "")),
        )
        if annotation.trade_id:
            annotations[annotation.trade_id] = annotation
    return annotations


def save_annotations(path: str | Path, annotations: dict[str, TradeAnnotation]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "annotations": [asdict(item) for item in annotations.values()],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_annotation_file(trades: list[ClosedTrade], path: str | Path) -> dict[str, TradeAnnotation]:
    annotations = load_annotations(path)
    changed = False
    for trade in trades:
        if trade.trade_id not in annotations:
            annotations[trade.trade_id] = TradeAnnotation(trade.trade_id)
            changed = True
    if changed or not Path(path).exists():
        save_annotations(path, annotations)
    return annotations


def update_annotation(path: str | Path, trade_id: str, values: dict[str, Any]) -> TradeAnnotation:
    annotations = load_annotations(path)
    current = annotations.get(trade_id, TradeAnnotation(trade_id))
    for field_name in asdict(current):
        if field_name in values and field_name != "trade_id":
            setattr(current, field_name, values[field_name])
    current.plan_follow_score = score_alignment(current)
    annotations[trade_id] = current
    save_annotations(path, annotations)
    return current


def score_alignment(annotation: TradeAnnotation) -> int | None:
    if annotation.system_fit == "未标注" and annotation.plan_follow == "未标注":
        return None
    score = 0
    score += {"完全执行": 25, "轻微变形": 17, "明显变形": 8, "完全情绪化": 0}.get(annotation.plan_follow, 0)
    score += {"计划买点": 25, "提前买": 10, "追高买": 8, "翘板买": 5, "补救买": 4, "随手买": 0}.get(annotation.buy_quality, 0)
    score += {"合理": 25, "偏重": 15, "过重": 5, "连续盈利后放大": 0, "亏损后加仓": 0}.get(annotation.position_quality, 0)
    score += {"严格执行": 25, "延迟执行": 12, "没有执行": 0, "不适用": 18}.get(annotation.stop_execution, 0)
    return score


def diagnose_behavior(trades: list[ClosedTrade], annotations: dict[str, TradeAnnotation]) -> BehaviorDiagnosis:
    rows = [merge_trade_annotation(trade, annotations.get(trade.trade_id)) for trade in trades]
    summary = compute_summary(rows)
    groups = {
        "system_in": compute_summary([row for row in rows if row["system_fit"] in SYSTEM_IN]),
        "partial": compute_summary([row for row in rows if row["system_fit"] == "部分符合"]),
        "system_out": compute_summary([row for row in rows if row["system_fit"] in SYSTEM_OUT]),
        "unannotated": compute_summary([row for row in rows if row["system_fit"] == "未标注"]),
    }
    simulations = compute_simulations(rows)
    emotion = compute_emotion_stats(rows)
    risk_model = compute_risk_model(rows)
    progress = compute_progress(rows)
    weekly_progress = compute_weekly_progress(rows)
    attribution = compute_attribution(rows, groups, simulations)
    conclusions = build_conclusions(summary, groups, simulations, emotion, risk_model, attribution)
    return BehaviorDiagnosis(
        trades=rows,
        annotations={key: asdict(value) for key, value in annotations.items()},
        summary=summary,
        groups=groups,
        simulations=simulations,
        emotion=emotion,
        risk_model=risk_model,
        progress=progress,
        weekly_progress=weekly_progress,
        attribution=attribution,
        conclusions=conclusions,
    )


def merge_trade_annotation(trade: ClosedTrade, annotation: TradeAnnotation | None) -> dict[str, Any]:
    annotation = annotation or TradeAnnotation(trade.trade_id)
    score = annotation.plan_follow_score if annotation.plan_follow_score is not None else score_alignment(annotation)
    row = asdict(trade)
    row.update(asdict(annotation))
    row["plan_follow_score"] = score
    row["quality_label"] = quality_label(row)
    return row


def quality_label(row: dict[str, Any]) -> str:
    score = row.get("plan_follow_score")
    if row.get("system_fit") in SYSTEM_IN and score is not None and score >= 80:
        return "好交易"
    if row.get("system_fit") in SYSTEM_OUT and (row.get("emotion_state") in EMOTION_RISK or row.get("position_quality") in BAD_POSITION):
        return "坏交易"
    if row.get("pnl", 0) > 0 and row.get("system_fit") in SYSTEM_OUT:
        return "违规盈利"
    if row.get("pnl", 0) < 0 and row.get("system_fit") in SYSTEM_IN and score is not None and score >= 80:
        return "有效试错"
    return "待复盘"


def compute_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    pnl = sum(float(row.get("pnl", 0)) for row in rows)
    buy_amount = sum(float(row.get("buy_amount", 0)) for row in rows)
    wins = [row for row in rows if row.get("pnl", 0) > 0]
    losses = [row for row in rows if row.get("pnl", 0) < 0]
    avg_win = sum(row["pnl"] for row in wins) / len(wins) if wins else 0.0
    avg_loss = sum(row["pnl"] for row in losses) / len(losses) if losses else 0.0
    return {
        "count": total,
        "pnl": round(pnl, 2),
        "buy_amount": round(buy_amount, 2),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(len(wins) / total * 100, 1) if total else 0.0,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "payoff_ratio": round(avg_win / abs(avg_loss), 2) if avg_loss else None,
        "expectancy": round(pnl / total, 2) if total else 0.0,
        "turnover_return": round(pnl / buy_amount * 100, 2) if buy_amount else 0.0,
        "severe_loss_count": sum(1 for row in rows if row.get("return_pct", 0) <= -0.03),
        "annotated_count": sum(1 for row in rows if row.get("system_fit") != "未标注"),
    }


def compute_simulations(rows: list[dict[str, Any]]) -> dict[str, Any]:
    actual = sum(row["pnl"] for row in rows)
    without_system_out = sum(row["pnl"] for row in rows if row.get("system_fit") not in SYSTEM_OUT)
    avoidable_loss_half_reduced = actual + sum(abs(row["pnl"]) * 0.5 for row in avoidable_loss_rows(rows))
    strict_stop = sum(max(row["pnl"], -0.03 * row["buy_amount"]) for row in rows)
    half_after_three_wins = 0.0
    out_position_cap = 0.0
    no_afternoon_emotion = 0.0
    for row in rows:
        pnl = row["pnl"]
        half_after_three_wins += pnl * 0.5 if row.get("win_streak_before", 0) >= 3 else pnl
        out_position_cap += pnl * 0.2 if row.get("system_fit") in SYSTEM_OUT else pnl
        if row.get("buy_time_bucket") == "午后/临近午盘" and row.get("emotion_state") in EMOTION_RISK:
            continue
        no_afternoon_emotion += pnl
    return {
        "actual_pnl": round(actual, 2),
        "without_system_out_pnl": round(without_system_out, 2),
        "avoidable_loss_half_reduced_pnl": round(avoidable_loss_half_reduced, 2),
        "strict_stop_3pct_pnl": round(strict_stop, 2),
        "half_size_after_three_wins_pnl": round(half_after_three_wins, 2),
        "system_out_20pct_size_pnl": round(out_position_cap, 2),
        "no_afternoon_emotion_pnl": round(no_afternoon_emotion, 2),
    }


def avoidable_loss_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("pnl", 0) < 0 and row.get("avoidable_loss") == "YES"]


def system_out_loss_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("pnl", 0) < 0 and row.get("system_fit") in SYSTEM_OUT]


def compute_attribution(
    rows: list[dict[str, Any]],
    groups: dict[str, dict[str, Any]],
    simulations: dict[str, Any],
) -> dict[str, Any]:
    total = len(rows)
    total_loss = sum(abs(row["pnl"]) for row in rows if row.get("pnl", 0) < 0)
    avoidable_rows = avoidable_loss_rows(rows)
    avoidable_amount = sum(abs(row["pnl"]) for row in avoidable_rows)
    system_out_loss = sum(abs(row["pnl"]) for row in system_out_loss_rows(rows))
    error_stats: dict[str, dict[str, Any]] = {}
    for row in rows:
        for code in row.get("error_codes", []):
            if code not in ERROR_CODES:
                continue
            stat = error_stats.setdefault(
                code,
                {"code": code, "name": ERROR_CODES[code], "count": 0, "loss_amount": 0.0, "pnl": 0.0},
            )
            stat["count"] += 1
            stat["pnl"] += row.get("pnl", 0)
            if row.get("pnl", 0) < 0:
                stat["loss_amount"] += abs(row["pnl"])
    ranked_errors = sorted(
        (
            {
                **stat,
                "loss_amount": round(stat["loss_amount"], 2),
                "pnl": round(stat["pnl"], 2),
            }
            for stat in error_stats.values()
        ),
        key=lambda item: (item["loss_amount"], item["count"]),
        reverse=True,
    )
    return {
        "mode_in_ratio": round(groups["system_in"]["count"] / total * 100, 1) if total else 0.0,
        "system_out_loss_amount": round(system_out_loss, 2),
        "system_out_loss_ratio": round(system_out_loss / total_loss * 100, 1) if total_loss else 0.0,
        "total_loss_amount": round(total_loss, 2),
        "avoidable_loss_amount": round(avoidable_amount, 2),
        "avoidable_loss_ratio": round(avoidable_amount / total_loss * 100, 1) if total_loss else 0.0,
        "avoidable_loss_half_reduced_pnl": simulations["avoidable_loss_half_reduced_pnl"],
        "without_system_out_pnl": simulations["without_system_out_pnl"],
        "error_code_stats": ranked_errors,
        "biggest_error_code": ranked_errors[0] if ranked_errors else None,
    }


def compute_emotion_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "连续盈利3笔后": [row for row in rows if row.get("win_streak_before", 0) >= 3],
        "连续亏损后": [row for row in rows if row.get("loss_streak_before", 0) >= 1],
        "午后/临近午盘": [row for row in rows if row.get("buy_time_bucket") == "午后/临近午盘"],
        "情绪风险交易": [row for row in rows if row.get("emotion_state") in EMOTION_RISK],
        "FOMO/怕踏空": [
            row
            for row in rows
            if row.get("emotion_state") == "FOMO" or "怕踏空" in row.get("emotion_sources", [])
        ],
    }
    return {name: compute_summary(items) for name, items in buckets.items()}


def compute_risk_model(rows: list[dict[str, Any]]) -> dict[str, Any]:
    baseline = kelly_profile("基础样本", rows, cap=0.5)
    base_position = baseline["recommended_position_pct"] / 100
    after_three_wins = kelly_profile(
        "连续盈利3笔后",
        [row for row in rows if row.get("win_streak_before", 0) >= 3],
        cap=0.35,
        max_recommended=base_position * 0.5,
        overlay_reason="连续盈利后防止自信膨胀，建议不高于基础仓位的一半。",
    )
    after_severe_loss = kelly_profile(
        "出现-3%以上亏损后的恢复期",
        rows_after_severe_loss(rows),
        cap=0.25,
        max_recommended=base_position * 0.5,
        overlay_reason="出现大亏后先恢复执行一致性，建议不高于基础仓位的一半。",
    )
    after_emotion_risk = kelly_profile(
        "情绪风险状态",
        [row for row in rows if row.get("emotion_state") in EMOTION_RISK],
        cap=0.2,
    )
    return {
        "formula": "Kelly = p - (1-p)/b；p=胜率，b=平均盈利/平均亏损绝对值。实盘建议使用半凯利，并按状态设置上限。",
        "profiles": [baseline, after_three_wins, after_severe_loss, after_emotion_risk],
    }


def rows_after_severe_loss(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    severe_seen = False
    for row in rows:
        if severe_seen:
            result.append(row)
        if row.get("return_pct", 0) <= -0.03:
            severe_seen = True
    return result


def kelly_profile(
    name: str,
    rows: list[dict[str, Any]],
    cap: float,
    max_recommended: float | None = None,
    overlay_reason: str = "",
) -> dict[str, Any]:
    summary = compute_summary(rows)
    p = summary["win_rate"] / 100 if summary["count"] else 0.0
    b = summary["payoff_ratio"] or 0.0
    if summary["count"] < 5 or b <= 0:
        raw_kelly = 0.0
        reason = "样本不足，按风险控制处理。"
    else:
        raw_kelly = p - (1 - p) / b
        reason = "负凯利代表该状态不具备下注优势。" if raw_kelly <= 0 else "使用半凯利并受状态上限约束。"
    half_kelly = max(0.0, raw_kelly * 0.5)
    recommended = min(half_kelly, cap)
    if summary["expectancy"] <= 0:
        recommended = 0.0
    if max_recommended is not None:
        recommended = min(recommended, max_recommended)
        if overlay_reason:
            reason = f"{reason} {overlay_reason}"
    return {
        "name": name,
        "sample_size": summary["count"],
        "win_rate": summary["win_rate"],
        "payoff_ratio": summary["payoff_ratio"],
        "expectancy": summary["expectancy"],
        "raw_kelly_pct": round(raw_kelly * 100, 1),
        "half_kelly_pct": round(half_kelly * 100, 1),
        "cap_pct": round(cap * 100, 1),
        "recommended_position_pct": round(recommended * 100, 1),
        "reason": reason,
    }


def compute_progress(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        date_key = str(row["sell_time"])[:10]
        by_date.setdefault(date_key, []).append(row)
    progress = []
    for date_key in sorted(by_date):
        items = by_date[date_key]
        scores = [row["plan_follow_score"] for row in items if row.get("plan_follow_score") is not None]
        progress.append(
            {
                "date": date_key,
                "pnl": round(sum(row["pnl"] for row in items), 2),
                "alignment_score": round(sum(scores) / len(scores), 1) if scores else None,
                "system_in_ratio": round(
                    sum(1 for row in items if row.get("system_fit") in SYSTEM_IN) / len(items) * 100, 1
                )
                if items
                else 0,
                "emotion_trade_count": sum(1 for row in items if row.get("emotion_state") in EMOTION_RISK),
                "severe_loss_count": sum(1 for row in items if row.get("return_pct", 0) <= -0.03),
            }
        )
    return progress


def compute_weekly_progress(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_week: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        dt = datetime.fromisoformat(str(row["sell_time"]))
        iso = dt.isocalendar()
        week_key = f"{iso.year}-W{iso.week:02d}"
        by_week.setdefault(week_key, []).append(row)
    progress = []
    for week_key in sorted(by_week):
        items = by_week[week_key]
        scores = [row["plan_follow_score"] for row in items if row.get("plan_follow_score") is not None]
        progress.append(
            {
                "week": week_key,
                "pnl": round(sum(row["pnl"] for row in items), 2),
                "alignment_score": round(sum(scores) / len(scores), 1) if scores else None,
                "system_in_ratio": round(
                    sum(1 for row in items if row.get("system_fit") in SYSTEM_IN) / len(items) * 100, 1
                )
                if items
                else 0,
                "emotion_trade_count": sum(1 for row in items if row.get("emotion_state") in EMOTION_RISK),
                "severe_loss_count": sum(1 for row in items if row.get("return_pct", 0) <= -0.03),
                "trade_count": len(items),
            }
        )
    return progress


def build_conclusions(
    summary: dict[str, Any],
    groups: dict[str, dict[str, Any]],
    simulations: dict[str, Any],
    emotion: dict[str, dict[str, Any]],
    risk_model: dict[str, Any],
    attribution: dict[str, Any],
) -> list[str]:
    conclusions: list[str] = []
    annotated = summary.get("annotated_count", 0)
    if annotated == 0:
        conclusions.append("请先完成关键交易标注；系统不会在没有交易员确认时强判模式内外。以下仓位建议先基于交割单结果做风险控制参考。")
    system_in = groups["system_in"]
    system_out = groups["system_out"]
    if system_in["count"] and system_in["expectancy"] > 0 and system_out["count"] and system_out["expectancy"] < 0:
        conclusions.append("系统内交易具备正期望，优先问题是执行变形和模式外交易。")
    elif system_in["count"] and system_in["expectancy"] < 0:
        conclusions.append("系统内交易仍为负期望，需要回到入场逻辑本身做优化。")
    if system_out["pnl"] < 0:
        conclusions.append(f"模式外交易拖累 {abs(system_out['pnl']):.2f}，应先压缩到总交易的 10% 以下。")
    if attribution["avoidable_loss_amount"] > 0:
        conclusions.append(
            f"已标注可避免亏损 {attribution['avoidable_loss_amount']:.2f}，"
            f"占总亏损 {attribution['avoidable_loss_ratio']:.1f}%；若减少一半，本期盈亏约 {attribution['avoidable_loss_half_reduced_pnl']:.2f}。"
        )
    if attribution["biggest_error_code"]:
        biggest = attribution["biggest_error_code"]
        conclusions.append(f"当前最大错误编号是 {biggest['code']} {biggest['name']}，对应亏损 {biggest['loss_amount']:.2f}。")
    if emotion["连续盈利3笔后"]["count"] and emotion["连续盈利3笔后"]["pnl"] < 0:
        conclusions.append("连续盈利后的交易为负贡献，建议连续盈利 3 笔后自动降仓或休息。")
    if simulations["strict_stop_3pct_pnl"] > simulations["actual_pnl"]:
        delta = simulations["strict_stop_3pct_pnl"] - simulations["actual_pnl"]
        conclusions.append(f"若大亏控制在 -3%，本期可多保留约 {delta:.2f}。")
    for profile in risk_model["profiles"]:
        if profile["name"] == "连续盈利3笔后":
            conclusions.append(
                f"连续盈利3笔后的凯利建议仓位：{profile['recommended_position_pct']}%。"
                f"公式结果 raw={profile['raw_kelly_pct']}%，半凯利={profile['half_kelly_pct']}%，状态上限={profile['cap_pct']}%。"
            )
        if profile["name"] == "出现-3%以上亏损后的恢复期":
            conclusions.append(
                f"出现-3%以上亏损后的恢复期建议仓位：{profile['recommended_position_pct']}%。"
                f"该状态胜率 {profile['win_rate']}%，盈亏比 {profile['payoff_ratio']}，单笔期望 {profile['expectancy']}。"
            )
    return conclusions or ["当前样本未显示单一主导问题，请继续积累标注数据。"]


def write_behavior_report(diagnosis: BehaviorDiagnosis, output: str | Path) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = render_behavior_markdown(diagnosis)
    output.write_text(lines, encoding="utf-8")
    return output


def render_behavior_markdown(diagnosis: BehaviorDiagnosis) -> str:
    lines = ["# 交割单行为诊断报告", ""]
    lines.extend(["## 核心结论", ""])
    for item in diagnosis.conclusions:
        lines.append(f"- {item}")
    lines.extend(["", "## 总览", ""])
    lines.extend(summary_lines(diagnosis.summary))
    lines.extend(["", "## 模式分组", ""])
    for key, title in [("system_in", "系统内"), ("partial", "部分符合"), ("system_out", "系统外"), ("unannotated", "未标注")]:
        lines.append(f"### {title}")
        lines.extend(summary_lines(diagnosis.groups[key]))
        lines.append("")
    lines.extend(["## 修正模拟", ""])
    for key, value in diagnosis.simulations.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## 错误归因", ""])
    attr = diagnosis.attribution
    lines.append(f"- 模式内交易占比：{attr['mode_in_ratio']}%")
    lines.append(f"- 模式外亏损占比：{attr['system_out_loss_ratio']}%")
    lines.append(f"- 可避免亏损金额：{attr['avoidable_loss_amount']}")
    lines.append(f"- 可避免亏损占比：{attr['avoidable_loss_ratio']}%")
    lines.append(f"- 可避免亏损减少 50% 后盈亏：{attr['avoidable_loss_half_reduced_pnl']}")
    lines.append(f"- 去掉模式外交易后盈亏：{attr['without_system_out_pnl']}")
    if attr["error_code_stats"]:
        lines.extend(["", "| 错误编号 | 错误 | 次数 | 亏损金额 | 净盈亏 |", "| --- | --- | ---: | ---: | ---: |"])
        for item in attr["error_code_stats"]:
            lines.append(f"| {item['code']} | {item['name']} | {item['count']} | {item['loss_amount']} | {item['pnl']} |")
    lines.extend(["", "## 凯利仓位建议", "", diagnosis.risk_model["formula"], ""])
    for profile in diagnosis.risk_model["profiles"]:
        lines.append(
            f"- {profile['name']}：样本 {profile['sample_size']}，胜率 {profile['win_rate']}%，"
            f"盈亏比 {profile['payoff_ratio']}，raw Kelly {profile['raw_kelly_pct']}%，"
            f"半凯利 {profile['half_kelly_pct']}%，建议仓位 {profile['recommended_position_pct']}%。"
        )
    lines.extend(["", "## 大肉与大亏", ""])
    key_trades = [row for row in diagnosis.trades if "大肉" in row.get("rank_tag", "") or "大亏" in row.get("rank_tag", "")]
    lines.extend(["| 交易 | 买入 | 卖出 | 盈亏 | 收益率 | 标注 | 质量 |", "| --- | --- | --- | ---: | ---: | --- | --- |"])
    for row in key_trades:
        lines.append(
            f"| {row['code']} {row['name']} | {row['buy_time']} | {row['sell_time']} | "
            f"{row['pnl']:.2f} | {row['return_pct'] * 100:.2f}% | {row['system_fit']} | {row['quality_label']} |"
        )
    return "\n".join(lines) + "\n"


def summary_lines(summary: dict[str, Any]) -> list[str]:
    return [
        f"- 笔数：{summary['count']}",
        f"- 盈亏：{summary['pnl']}",
        f"- 胜率：{summary['win_rate']}%",
        f"- 平均盈利/亏损：{summary['avg_win']} / {summary['avg_loss']}",
        f"- 盈亏比：{summary['payoff_ratio']}",
        f"- 单笔期望：{summary['expectancy']}",
        f"- 严重亏损：{summary['severe_loss_count']} 笔",
    ]
