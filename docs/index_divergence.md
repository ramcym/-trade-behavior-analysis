# 大盘指数背离分析

## 本地日线文件

```powershell
$env:PYTHONPATH="src"
python -m trade_review.cli --index-daily data/market/000001_daily.csv --index-name 上证指数 --divergence-output reports/000001_divergence.md
```

日线文件支持 CSV/XLSX，常见列名会自动识别：

- 日期: `日期`、`交易日期`、`date`、`trade_date`
- 开高低收: `开盘`、`最高`、`最低`、`收盘`，或 `open`、`high`、`low`、`close`
- 成交量/成交额: `成交量`、`成交额`，或 `volume`、`amount`

## 自动读取 AKShare

安装 AKShare 后，可以直接读取指数日线：

```powershell
$env:PYTHONPATH="src"
python -m trade_review.cli --index-code 000001 --index-start 20200101 --index-end 20260613 --index-name 上证指数
```

常用指数代码：

- `000001`: 上证指数
- `399001`: 深证成指
- `399006`: 创业板指

## 背离规则

默认使用 MACD 柱：

- 顶背离: 指数局部高点创新高，但指标未创新高。
- 底背离: 指数局部低点创新低，但指标未创新低。

可以切换指标：

```powershell
python -m trade_review.cli --index-daily data/market/000001_daily.csv --divergence-indicator rsi
python -m trade_review.cli --index-daily data/market/000001_daily.csv --divergence-indicator dif
python -m trade_review.cli --index-daily data/market/000001_daily.csv --divergence-indicator volume
```

调节灵敏度：

```powershell
python -m trade_review.cli --index-daily data/market/000001_daily.csv --pivot-window 1 --min-price-change-pct 0.001
```
