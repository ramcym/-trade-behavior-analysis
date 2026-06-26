# Trading System Spec

This project diagnoses trade behavior before judging whether the trading system itself is valid. The first goal is to separate market losses from execution errors.

## Core Principle

A good trade is not defined by profit alone. A good trade is:

- Planned before entry.
- Consistent with the trader's own system.
- Sized according to current emotional and risk state.
- Exited according to the same logic used for entry.

## Trade Tags

Each closed trade can be annotated with these fields.

### trade_type

- `CORE_LEADER`: 核心龙头
- `MID_CORE`: 次核心
- `FOLLOWER`: 跟风/杂毛
- `EMOTION_TRADE`: 情绪单

### entry_model

- `IGNITION`: 点火一致买入
- `DIVERGENCE`: 底背离/分歧低吸
- `CHASE_HIGH`: 追高
- `RANDOM`: 无明确模式

### market_condition

- `INDEX_UP`: 大盘向上
- `INDEX_DOWN`: 大盘下杀
- `INDEX_FLAT`: 大盘震荡

### sector_condition

- `SECTOR_STRONG`: 板块强势
- `SECTOR_WEAK`: 板块转弱
- `SECTOR_DIVERGE`: 板块分歧

### stock_position

- `FIRST_CHOICE`: 市场第一选择
- `SECOND_CHOICE`: 第二选择
- `NOT_CORE`: 非核心

### signal_quality

- `FULL_CONFIRM`: 大盘+板块+个股+点火全部满足
- `MISSING_ONE`: 缺一项
- `MISSING_MULTI`: 缺多项

### exit_reason

- `STOP_LOSS`: 止损
- `TAKE_PROFIT`: 止盈
- `SECTOR_DIVERGENCE`: 板块背离
- `STOCK_DIVERGENCE`: 个股背离
- `INDEX_WEAKNESS`: 指数走弱
- `RULE_VIOLATION`: 规则违反

## Avoidable Loss

Every losing trade should answer:

- `avoidable_loss`: `YES` / `NO`
- `avoidable_reason`: why the loss could have been avoided.
- `error_codes`: one or more error codes from `docs/ERROR_CODES.md`.

The system then calculates:

- Total loss.
- Avoidable loss amount.
- Avoidable loss ratio.
- PnL if avoidable losses are reduced by 50%.
- PnL if all mode-out trades are removed.

## Priority Improvement Areas

The system should prioritize:

1. Error attribution.
2. Avoidable loss control.
3. Discipline after consecutive wins.

