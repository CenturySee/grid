# TODO

## 网格策略 2.0

### 2.1 留利润

- [ ] 在配置文件中增加 `strategy_version` 和 `retain_profit` 配置区块。
- [ ] 支持 `retain_profit.enabled` 开关。
- [ ] 支持 `retain_profit.multiplier`，用于普通留利润、留双份利润等变体。
- [ ] 在计划报告中展示留利润配置和估算字段。
- [ ] 在回测中支持部分卖出：卖出回收本金，剩余份额作为留存仓位。
- [ ] 回测交易记录增加 `sold_shares`、`retained_shares`、`retained_value`、`recover_cost`、`sell_mode`。
- [ ] 回测摘要增加留存份额、留存市值、留存成本、留存仓位贡献。

### 2.2 逐格加码增强

- [ ] 扩展投入金额规则，支持从第 N 格开始加码。
- [ ] 支持等差递增：`amount_mode: arithmetic` + `amount_step` + `scale_start_level`。
- [ ] 支持等比递增：`amount_mode: geometric` + `amount_ratio` + `scale_start_level`。
- [ ] 在压力测试摘要中展示加码规则、最大资金占用和资金是否覆盖到底部。
- [ ] 补充对应的计划报告和回测输出字段。

### 2.3 一网打尽

- [ ] 设计多网格配置结构，支持小网、中网、大网。
- [ ] 每个子网格支持独立 `grid_pct`、投入金额、加码规则和留利润规则。
- [ ] 计划表增加 `grid_name` 字段，区分不同子网格。
- [ ] 回测支持多子网格共用资金池。
- [ ] 回测输出按 `grid_name` 汇总交易次数、已实现利润、留存市值、资金占用。
- [ ] 报告中增加多网格整体摘要和分网格摘要。

### 实施顺序

1. 先实现 2.1 留利润。
2. 再实现 2.2 逐格加码增强。
3. 最后实现 2.3 一网打尽。

