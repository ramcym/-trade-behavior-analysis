# Questionnaire Fields

The review form should force the trader to answer whether the trade matched the plan, instead of judging by profit alone.

## Required Questions

1. 这笔交易是否属于核心龙头？
2. 它是不是今天市场第一选择？
3. 大盘是否配合？
4. 板块是否配合？
5. 个股是否配合？
6. 是否有点火确认？
7. 是否存在顶背离？
8. 是否连续盈利后出手？
9. 是否因为错过第一目标而买了第二目标？
10. 如果今天只能买一只股票，我还会买它吗？
11. 这笔交易是系统内，还是系统外？
12. 如果亏损，这笔亏损是否可避免？

## Implementation Mapping

| Question | Field |
| --- | --- |
| 是否属于核心龙头 | `trade_type` |
| 是否市场第一选择 | `stock_position` |
| 大盘是否配合 | `market_condition` |
| 板块是否配合 | `sector_condition` |
| 个股是否配合 | `signal_quality` |
| 是否有点火确认 | `entry_model`, `signal_quality` |
| 是否存在顶背离 | `error_codes=E03` or notes |
| 是否连续盈利后出手 | `win_streak_before`, `error_codes=E02` |
| 是否买了第二目标 | `stock_position=SECOND_CHOICE`, `error_codes=E04` |
| 只能买一只还会买吗 | `stock_position`, `notes` |
| 系统内还是系统外 | `system_fit` |
| 亏损是否可避免 | `avoidable_loss`, `avoidable_reason`, `error_codes` |

