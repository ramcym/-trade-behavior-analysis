from __future__ import annotations

from pathlib import Path

from .models import TradeReview


def render_markdown(reviews: list[TradeReview]) -> str:
    lines: list[str] = ["# 交割单复盘报告", ""]
    if not reviews:
        lines.extend(["未发现买入记录。", ""])
        return "\n".join(lines)

    total = len(reviews)
    matched = sum(1 for item in reviews if item.conclusion.value == "符合体系")
    partial = sum(1 for item in reviews if item.conclusion.value == "部分符合")
    unknown = sum(1 for item in reviews if item.conclusion.value == "无法判断")
    mismatch = total - matched - partial - unknown
    lines.extend(
        [
            "## 总览",
            "",
            f"- 买入记录：{total} 笔",
            f"- 符合体系：{matched} 笔",
            f"- 部分符合：{partial} 笔",
            f"- 不符合：{mismatch} 笔",
            f"- 无法判断：{unknown} 笔",
            "",
        ]
    )

    for idx, review in enumerate(reviews, 1):
        trade = review.trade
        title = f"{idx}. {trade.trade_dt:%Y-%m-%d %H:%M:%S} {trade.code} {trade.name}".strip()
        lines.extend(
            [
                f"## {title}",
                "",
                f"- 买点类型：{review.buy_point_type.value}",
                f"- 结论：{review.conclusion.value}",
                f"- 成交：{trade.price:.3f} / {trade.quantity:.0f} 股 / {trade.amount:.2f}",
                f"- 题材状态：{review.topic_status}",
                "",
                "| 项目 | 判断 | 证据 |",
                "| --- | --- | --- |",
            ]
        )
        for evidence in review.evidences:
            if evidence.passed is True:
                flag = "通过"
            elif evidence.passed is False:
                flag = "未通过"
            else:
                flag = "无法判断"
            lines.append(f"| {evidence.name} | {flag} | {evidence.detail} |")
        lines.extend(["", f"**改进建议：** {review.suggestion}", ""])
    return "\n".join(lines)


def write_markdown(reviews: list[TradeReview], output: str | Path) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(reviews), encoding="utf-8")
    return output
