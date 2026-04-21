# Grid Strategy Planner

网格策略 1.0 计划生成与轻量历史回放工具。

当前版本聚焦两件事：

- 生成网格交易计划表，并完成底部压力测试。
- 使用前复权日线数据做轻量历史回放，观察历史触发、资金占用、浮亏和收益表现。

> 说明：本项目目前是研究与辅助决策工具，不包含实盘交易接口，也不构成投资建议。

## 功能

- 支持固定首网价格。
- 支持从复权历史高点回撤生成首网价格。
- 支持固定底部价格。
- 支持从首网价格继续回撤生成压力测试底部。
- 网格价格使用固定价差：`grid_step = first_price * grid_pct`。
- 支持每网等额投入、等差递增投入。
- 支持交易单位、手续费、最低手续费、滑点。
- 支持本地通达信离线行情读取。
- 支持通过 `opentdx` 获取除权除息复权因子。
- 计划与回测默认使用前复权数据。
- 计划和回测输出中的浮点数统一保留三位小数。
- 支持 YAML/JSON 配置文件。
- 输出 CSV 和 Markdown 报告。

## 环境

推荐使用 `py312` 环境：

```powershell
conda activate py312
```

或直接使用环境中的 Python：

```powershell
& 'C:\Users\xzq-telecom\miniconda3\envs\py312\python.exe' --version
```

依赖包：

```powershell
& 'C:\Users\xzq-telecom\miniconda3\envs\py312\python.exe' -m pip install pandas pyyaml pytdx opentdx
```

## 数据

本地行情使用通达信离线日线数据：

```text
C:/new_tdx/vipdoc/sh
C:/new_tdx/vipdoc/sz
C:/new_tdx/vipdoc/bj
```

离线行情是不复权数据。程序会通过 `opentdx` 获取复权因子，并将历史价格转换为复权口径。

当前轻量回测强制使用前复权：

```yaml
adjust_method: forward
```

## 配置

示例配置：

[configs/sample_grid_plan.yaml](configs/sample_grid_plan.yaml)

常用字段：

- `symbol`：标的代码，例如 `sh510300`。
- `first_price_mode`：首网点位模式，支持 `fixed`、`drawdown_from_high`。
- `first_price`：固定首网价格。
- `high_drawdown_pct`：从历史高点回撤比例。
- `start_date` / `end_date`：历史统计和回测区间；留空表示使用全部可读历史。
- `grid_pct`：网格比例。
- `bottom_mode`：底部模式，支持 `fixed`、`drawdown_from_first`。
- `bottom_price`：固定底部价格。
- `bottom_drawdown_pct`：从首网继续回撤比例。
- `first_amount`：第一网计划投入金额。
- `amount_mode`：投入模式，支持 `equal`、`arithmetic`。
- `amount_step`：等差递增步长。
- `lot_size`：交易单位。
- `fee_rate`：单边手续费率。
- `min_fee`：单笔最低手续费。
- `slippage_rate`：单边滑点率。
- `price_digits`：价格保留位数，建议为 `3`。
- `basename`：输出文件名前缀。

## 生成网格计划

```powershell
& 'C:\Users\xzq-telecom\miniconda3\envs\py312\python.exe' .\scripts\generate_grid_plan.py --config .\configs\sample_grid_plan.yaml
```

输出文件：

```text
outputs/{basename}_levels.csv
outputs/{basename}_summary.csv
outputs/{basename}_report.md
```

计划报告包含：

- 压力测试摘要。
- 首网价格区间统计。
- 网格明细。
- 风险提示。

## 轻量历史回放

```powershell
& 'C:\Users\xzq-telecom\miniconda3\envs\py312\python.exe' .\scripts\backtest_grid_v1.py --config .\configs\sample_grid_plan.yaml
```

输出文件：

```text
outputs/{basename}_backtest_trades.csv
outputs/{basename}_backtest_equity.csv
outputs/{basename}_backtest_days.csv
outputs/{basename}_backtest_summary.csv
outputs/{basename}_backtest_report.md
```

回测规则：

- 使用前复权日线数据。
- `low <= buy_price` 触发买入。
- `high >= sell_price` 触发卖出。
- 如果开盘直接越过买入价或卖出价，按开盘价成交并标记为 `gap_open`。
- 同一天可能触发多个网格。
- 每个网格同一时间只持有一笔。
- 采用保守日线回放：同一天新买入的网格不会在当天卖出。

## 目录

```text
configs/              示例配置
references/           网格策略参考资料
scripts/              命令行入口与参考脚本
src/                  核心代码
grid_v1.md            1.0 计划设计草稿
rules.md              本地环境与数据规则
```

`outputs/` 为生成结果目录，已加入 `.gitignore`。

## Web 工作台

当前提供一个本地 Web 工作台，用于交互式调整参数、查看 K 线、生成网格计划并运行轻量回测。

启动后端：

```powershell
& 'C:\Users\xzq-telecom\miniconda3\envs\py312\python.exe' -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

启动前端：

```powershell
cd frontend
npm install
npm run dev
```

默认访问：

```text
http://127.0.0.1:5173
```

前端接口默认连接：

```text
http://127.0.0.1:8000
```

如需调整后端地址，可以在前端设置环境变量：

```powershell
$env:VITE_API_BASE="http://127.0.0.1:8000"
npm run dev
```
