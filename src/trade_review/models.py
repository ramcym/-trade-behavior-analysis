from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class BuyPointType(str, Enum):
    IGNITION = "第一买点"
    SECOND_DIP = "第二买点"
    OTHER = "其他买点"
    UNKNOWN = "无法判断"


class ReviewConclusion(str, Enum):
    MATCH = "符合体系"
    PARTIAL = "部分符合"
    MISMATCH = "不符合"
    UNKNOWN = "无法判断"


@dataclass(frozen=True)
class Trade:
    trade_dt: datetime
    code: str
    name: str
    side: str
    price: float
    quantity: float = 0.0
    amount: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IntradayPoint:
    ts: datetime
    price: float
    volume: float = 0.0
    amount: float = 0.0
    side: str = ""


@dataclass
class SignalEvidence:
    name: str
    passed: bool | None
    detail: str
    score: int = 0


@dataclass
class TradeReview:
    trade: Trade
    buy_point_type: BuyPointType
    conclusion: ReviewConclusion
    evidences: list[SignalEvidence]
    suggestion: str
    topic_status: str = "题材无法确认"
