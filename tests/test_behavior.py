from pathlib import Path

from trade_review.behavior import (
    TradeAnnotation,
    diagnose_behavior,
    ensure_annotation_file,
    load_closed_trades,
    score_alignment,
    update_annotation,
)
from trade_review.behavior_server import BehaviorState, safe_filename


def test_load_current_delivery_note_generates_closed_trades():
    path = Path.cwd() / "最近一个月交割单数据.xls"

    trades = load_closed_trades(path)

    assert len(trades) == 23
    assert any(trade.code == "000725" and trade.pnl > 1000 for trade in trades)
    assert any(trade.code == "002185" and trade.return_pct < -0.07 for trade in trades)


def test_alignment_score_rewards_execution_quality():
    annotation = TradeAnnotation(
        trade_id="T1",
        plan_follow="完全执行",
        buy_quality="计划买点",
        position_quality="合理",
        stop_execution="严格执行",
    )

    assert score_alignment(annotation) == 100


def test_diagnosis_separates_system_out(tmp_path):
    path = Path.cwd() / "最近一个月交割单数据.xls"
    trades = load_closed_trades(path)
    annotation_path = tmp_path / "annotations.json"
    annotations = ensure_annotation_file(trades, annotation_path)

    for trade in trades:
        if trade.code in {"000725", "600396"}:
            update_annotation(
                annotation_path,
                trade.trade_id,
                {
                    "system_fit": "完全符合",
                    "plan_follow": "完全执行",
                    "emotion_state": "冷静",
                    "buy_quality": "计划买点",
                    "position_quality": "合理",
                    "stop_execution": "严格执行",
                },
            )
        elif trade.code in {"002185", "002361"}:
            update_annotation(
                annotation_path,
                trade.trade_id,
                {
                    "system_fit": "完全不符合",
                    "plan_follow": "完全情绪化",
                    "emotion_state": "急于修复",
                    "buy_quality": "追高买",
                    "position_quality": "过重",
                    "stop_execution": "没有执行",
                },
            )
    annotations = ensure_annotation_file(trades, annotation_path)
    diagnosis = diagnose_behavior(trades, annotations)

    assert diagnosis.groups["system_in"]["pnl"] > 0
    assert diagnosis.groups["system_out"]["pnl"] < 0
    assert any("执行" in item for item in diagnosis.conclusions)


def test_risk_model_produces_kelly_position_profiles():
    path = Path.cwd() / "最近一个月交割单数据.xls"
    trades = load_closed_trades(path)
    diagnosis = diagnose_behavior(trades, {})

    profiles = {item["name"]: item for item in diagnosis.risk_model["profiles"]}

    assert "连续盈利3笔后" in profiles
    assert "出现-3%以上亏损后的恢复期" in profiles
    assert 0 <= profiles["连续盈利3笔后"]["recommended_position_pct"] <= 35
    assert 0 <= profiles["出现-3%以上亏损后的恢复期"]["recommended_position_pct"] <= 25


def test_import_delivery_note_switches_state(tmp_path):
    path = Path.cwd() / "最近一个月交割单数据.xls"
    state = BehaviorState(path, tmp_path / "annotations.json", tmp_path / "report.md", tmp_path / "imports")
    payload = path.read_bytes()

    import base64

    data = state.import_delivery_note("新交割单.xls", base64.b64encode(payload).decode("ascii"))

    assert data["diagnosis"]["summary"]["count"] == 23
    assert state.trades_path.exists()
    assert state.annotations_path.exists()
    assert state.trades_path.parent == tmp_path / "imports"


def test_progress_has_daily_and_weekly_series():
    path = Path.cwd() / "最近一个月交割单数据.xls"
    trades = load_closed_trades(path)
    diagnosis = diagnose_behavior(trades, {})

    assert diagnosis.progress
    assert diagnosis.weekly_progress
    assert "week" in diagnosis.weekly_progress[0]


def test_safe_filename_keeps_supported_suffix():
    assert safe_filename("../坏 文件.xls").endswith(".xls")


def test_delivery_note_with_new_column_order_generates_closed_trades():
    path = Path.cwd() / "交割单6.25.xls"
    if not path.exists():
        return

    trades = load_closed_trades(path)

    assert len(trades) == 22
    assert any(trade.code == "000690" and trade.pnl < 0 for trade in trades)
    assert any(trade.code == "000725" and trade.pnl > 1000 for trade in trades)


def test_attribution_tracks_avoidable_loss_and_error_codes(tmp_path):
    path = Path.cwd() / "最近一个月交割单数据.xls"
    trades = load_closed_trades(path)
    annotation_path = tmp_path / "annotations.json"
    annotations = ensure_annotation_file(trades, annotation_path)
    loser = next(trade for trade in trades if trade.pnl < 0)

    update_annotation(
        annotation_path,
        loser.trade_id,
        {
            "system_fit": "完全不符合",
            "avoidable_loss": "YES",
            "avoidable_reason": "没有及时止损",
            "error_codes": ["E08"],
        },
    )
    annotations = ensure_annotation_file(trades, annotation_path)
    diagnosis = diagnose_behavior(trades, annotations)

    assert diagnosis.attribution["avoidable_loss_amount"] > 0
    assert diagnosis.attribution["avoidable_loss_ratio"] > 0
    assert diagnosis.attribution["biggest_error_code"]["code"] == "E08"
    assert diagnosis.simulations["avoidable_loss_half_reduced_pnl"] > diagnosis.simulations["actual_pnl"]
