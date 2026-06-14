# 交割单行为诊断系统

这是一个本地运行的交割单分析工具，重点不是直接判断交易系统好坏，而是先诊断交易者是否按自己的计划执行。

它通过交割单和人工标注，量化交易中的知行合一问题，识别情绪化交易、模式外交易、仓位失控、止损不执行等执行偏差，并重新计算剔除这些偏差后的交易表现。

核心目标：

- 判断亏损主要来自交易系统，还是来自执行变形。
- 用问卷式标注记录每笔交易的计划执行、开仓情绪、买点质量、仓位纪律和止损纪律。
- 区分“盈利但乱做”和“亏损但按计划执行”，避免只用盈亏评价交易质量。
- 计算模式内/模式外交易表现、知行合一分、情绪风险和仓位建议。
- 生成每日、每周进步曲线，让交易改进可视化。

## 新手推荐方式

如果你不会用命令行，可以先只做三件事：

1. 安装 Python 3.10 或以上版本。
2. 下载项目，解压后进入项目目录。
3. Windows 用户双击运行 `start_windows.bat`。

项目会自动安装依赖，并启动本地 Web 页面：

```text
http://127.0.0.1:8765/
```

第一次运行时，如果你还没有准备交割单，系统会使用 `examples/trades_template.csv` 示例模板启动。你可以先看页面效果，再把自己的交割单放到 `data/trades.xls` 后重新启动。

## 快速开始：本地 Web 版

### 1. 安装 Python

请先安装 Python 3.10 或以上版本。

### 2. 下载项目

点击 GitHub 页面右上角绿色 `Code` 按钮，选择 `Download ZIP`，解压后进入项目目录。

### 3. 安装依赖

Windows PowerShell：

```powershell
pip install -r requirements.txt
```

Mac / Linux：

```bash
pip install -r requirements.txt
```

### 4. 准备交割单

在项目根目录新建 `data` 文件夹，把你的交割单放进去，例如：

```text
data/trades.xls
```

支持 `.xls`、`.xlsx`、`.csv`。如果你不确定格式，可以先打开 `examples/trades_template.csv` 看示例字段。

### 5. 启动 Web 系统

Windows PowerShell：

```powershell
$env:PYTHONPATH="src"
python -m trade_review.behavior_server --trades data/trades.xls --port 8765
```

Mac / Linux：

```bash
PYTHONPATH=src python -m trade_review.behavior_server --trades data/trades.xls --port 8765
```

### 6. 打开浏览器

访问：

```text
http://127.0.0.1:8765/
```

然后在页面里导入交割单、标注交易行为、查看诊断结果。

## 一键启动脚本

Windows：

```text
start_windows.bat
```

Mac / Linux：

```bash
chmod +x start_mac_linux.sh
./start_mac_linux.sh
```

脚本会自动按顺序寻找交割单：

1. `data/trades.xls`
2. `data/trades.xlsx`
3. `data/trades.csv`
4. `examples/trades_template.csv`

## 页面功能

v1 重点分析“是否按交易系统执行”，不依赖大盘、板块或个股分时。页面支持：

- 导入 `.xls`、`.xlsx`、`.csv` 交割单
- 自动生成闭合交易、大肉、大亏
- 问卷式人工标注交易是否符合模式、是否按计划执行、开仓情绪、买点质量、仓位质量、止损执行
- 计算知行合一分、模式内/模式外表现、凯利仓位建议
- 生成每日和每周进步曲线

## 行为诊断逻辑

系统会先将交易拆成闭合交易，再结合人工标注进行分组：

- 系统内交易：符合自己的交易模式，且计划执行较好。
- 部分符合交易：方向或逻辑接近，但执行存在变形。
- 系统外交易：明显偏离计划，常见于情绪驱动、冲动开仓、追高、补救单、赌一把。
- 未标注交易：只保留客观盈亏，不做主观归因。

报告会重点回答：

- 哪些亏损是市场试错成本，哪些亏损是自己执行造成的。
- 如果剔除完全不符合模式的交易，收益会变成多少。
- 如果大亏严格控制在预设止损内，收益会改善多少。
- 连续盈利、连续亏损或单笔大亏后，仓位应该如何下降。
- 最近一天和最近一周的执行质量是否在进步。

## 隐私说明

本项目默认忽略本地交易数据、人工标注、报告和导入文件，避免把个人交割单上传到公开仓库。

已忽略的本地目录和文件包括：

- `annotations/`
- `imports/`
- `reports/`
- `*.xls`
- `*.xlsx`
- `交易总结.txt`

### 可选：分时复盘命令

项目仍保留扩展接口，可在后续版本接入分时数据做更细的交易回放：

```powershell
python -m trade_review.cli --trades data/trades.xlsx --ticks-dir data/ticks --output reports/review.md
```

如果本地源码还没有安装成包，可用：

```powershell
$env:PYTHONPATH="src"
python -m trade_review.cli --trades data/trades.xlsx --ticks-dir data/ticks --market-dir data/market --output reports/review.md
```

## 输入文件

### 交割单

支持 `.csv`、`.xlsx`、`.xls`。字段会自动识别常见中文列名：

- 日期：`交易日期`、`成交日期`、`日期`
- 时间：`成交时间`、`交易时间`、`时间`
- 代码：`证券代码`、`股票代码`、`代码`
- 名称：`证券名称`、`股票名称`、`名称`
- 方向：`买卖方向`、`操作`、`业务名称`
- 价格：`成交价格`、`成交价`、`价格`
- 数量：`成交数量`、`成交股数`、`数量`
- 金额：`成交金额`、`金额`

### 个股逐笔/分时成交

放在 `--ticks-dir` 下，文件名建议包含股票代码和日期，例如：

```text
data/ticks/20240613_300750.csv
data/ticks/300750_20240613.xlsx
```

字段支持：

- 时间：`时间`、`成交时间`
- 价格：`价格`、`成交价`
- 成交量：`成交量`、`数量`、`成交手数`
- 方向：`方向`、`买卖方向`、`性质`，可选
- 金额：`金额`、`成交金额`，可选

### 大盘/板块分时

可通过 `--market-dir` 提供本地 CSV/XLSX，文件名建议：

```text
data/market/20240613_index_000001.csv
data/market/20240613_board_机器人.csv
```

行情字段支持：

- 时间：`时间`、`日期时间`
- 收盘/最新价：`收盘`、`最新价`、`价格`
- 开盘、高、低、成交量可选。

如果安装了 AKShare，工具会尝试自动补齐大盘和板块分时；若数据源不可用，会在报告中标记缺失，不做硬判定。

## 输出

行为诊断报告会输出：

- 实际收益
- 剔除模式外交易后的收益
- 严格止损后的模拟收益
- 连续盈利或大亏后的仓位建议
- 知行合一分
- 情绪化交易占比
- 日度和周度进步曲线
- 下一步改进建议

## 测试

```powershell
$env:PYTHONPATH="src"
python -m pytest
```
