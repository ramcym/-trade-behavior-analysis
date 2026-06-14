# 板块背离分析

用于读取历史每日涨幅前三板块，并输出可疑板块背离点。

## 本地文件

支持 CSV/XLSX。可以提供全量板块日涨幅，也可以只提供已经筛好的每日前三。

必要字段：

- 日期：`日期`、`交易日期`、`date`
- 板块：`板块`、`板块名称`、`名称`、`行业名称`、`概念名称`
- 涨幅：`涨幅`、`涨跌幅`、`涨跌幅(%)`、`pct_chg`

可选字段：

- 排名：`排名`、`rank`
- 成交额：`成交额`、`成交金额`
- 大盘涨幅：`大盘涨幅`、`指数涨幅`、`index_pct`

运行：

```powershell
$env:PYTHONPATH="src"
python -m trade_review.sector_divergence --input data/sectors.csv --output reports/sector_divergence.md
```

## AKShare

安装 AKShare 后可按日期区间抓取板块历史日线，再自动筛选每日前三：

```powershell
$env:PYTHONPATH="src"
python -m trade_review.sector_divergence --start-date 2024-01-01 --end-date 2024-06-30 --output reports/sector_divergence.md
```

## 背离规则

- 热点强于大盘：大盘不涨或下跌，但前三板块均值明显走强。
- 局部过热：大盘上涨有限，前三板块平均涨幅大幅领先。
- 龙头走弱：同一龙头板块连续进入前三，但涨幅递减；若成交额也递减，级别提高。
- 热点轮动：前三板块与前一交易日重合很少，且前一日龙头跌出前三。
- 前三内部背离：第一名涨幅显著高于第二、第三名均值，强度过度集中。
