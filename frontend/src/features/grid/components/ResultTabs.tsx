import { useState } from 'react'
import type { BacktestPayload, GridLevel, PlanPayload, TradeRecord } from '../types'
import { formatNumber, formatPct } from '../utils'

type Props = {
  plan: PlanPayload | null
  backtest: BacktestPayload | null
}

const tabs = ['网格计划', '压力测试', '回测指标', '交易记录', '权益曲线', '报告'] as const
type Tab = (typeof tabs)[number]

export function ResultTabs({ plan, backtest }: Props) {
  const [active, setActive] = useState<Tab>('网格计划')

  return (
    <section className="panel">
      <div className="panel-header">
        <div className="tabs">
          {tabs.map((tab) => (
            <button
              className={`tab ${active === tab ? 'active' : ''}`}
              key={tab}
              onClick={() => setActive(tab)}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>
      <div className="result-body">
        {active === '网格计划' && <PlanTable levels={plan?.levels ?? []} />}
        {active === '压力测试' && <SummaryView summary={plan?.summary ?? null} />}
        {active === '回测指标' && <SummaryView summary={backtest?.summary ?? null} />}
        {active === '交易记录' && <TradeTable trades={backtest?.trades ?? []} />}
        {active === '权益曲线' && <EquitySummary backtest={backtest} />}
        {active === '报告' && <ReportPreview plan={plan} backtest={backtest} />}
      </div>
    </section>
  )
}

function PlanTable({ levels }: { levels: GridLevel[] }) {
  if (!levels.length) return <Empty text="生成计划后显示网格明细" />
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>网格</th>
          <th>买入价</th>
          <th>卖出价</th>
          <th>计划金额</th>
          <th>份额</th>
          <th>实际投入</th>
          <th>预期利润</th>
          <th>累计资金</th>
          <th className="left">提示</th>
        </tr>
      </thead>
      <tbody>
        {levels.map((level) => (
          <tr key={level.level_index}>
            <td>{level.level_index}</td>
            <td>{formatNumber(level.buy_price)}</td>
            <td>{formatNumber(level.sell_price)}</td>
            <td>{formatNumber(level.planned_amount)}</td>
            <td>{level.shares}</td>
            <td>{formatNumber(level.actual_invested)}</td>
            <td>{formatNumber(level.expected_profit)}</td>
            <td>{formatNumber(level.cumulative_cost)}</td>
            <td className="left">{level.warning || '-'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function SummaryView({ summary }: { summary: Record<string, unknown> | null }) {
  if (!summary) return <Empty text="运行后显示摘要指标" />
  const items: Array<[string, unknown, 'number' | 'pct' | 'text']> = [
    ['最大资金占用', summary.max_capital_required ?? summary.max_capital_in_use, 'number'],
    ['底部浮亏', summary.floating_pnl_at_bottom ?? summary.max_floating_loss, 'number'],
    ['最大回撤', summary.max_drawdown, 'pct'],
    ['总收益率', summary.total_return, 'pct'],
    ['买入次数', summary.buy_count, 'text'],
    ['卖出次数', summary.sell_count, 'text'],
    ['未触发网格', summary.untouched_levels, 'text'],
    ['期末权益', summary.final_equity, 'number'],
  ]
  return (
    <div className="metric-grid">
      {items.map(([label, value, kind]) => (
        <div className="metric" key={label}>
          <label>{label}</label>
          <strong>{formatMetricValue(value, kind)}</strong>
        </div>
      ))}
    </div>
  )
}

function formatMetricValue(value: unknown, kind: 'number' | 'pct' | 'text') {
  if (kind === 'pct') return formatPct(value)
  if (kind === 'number') return formatNumber(value)
  return value == null || value === '' ? '-' : String(value)
}

function TradeTable({ trades }: { trades: TradeRecord[] }) {
  if (!trades.length) return <Empty text="运行回测后显示交易记录" />
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th className="left">日期</th>
          <th>动作</th>
          <th>网格</th>
          <th>计划价</th>
          <th>成交价</th>
          <th>份额</th>
          <th>金额</th>
          <th>利润</th>
          <th>触发</th>
        </tr>
      </thead>
      <tbody>
        {trades.slice(-200).map((trade, index) => (
          <tr key={`${trade.date}-${trade.action}-${trade.level_index}-${index}`}>
            <td className="left">{String(trade.date).slice(0, 10)}</td>
            <td>{trade.action}</td>
            <td>{trade.level_index}</td>
            <td>{formatNumber(trade.plan_price)}</td>
            <td>{formatNumber(trade.exec_price)}</td>
            <td>{trade.shares}</td>
            <td>{formatNumber(trade.net_amount)}</td>
            <td>{formatNumber(trade.realized_pnl)}</td>
            <td>{trade.trigger_type}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function EquitySummary({ backtest }: { backtest: BacktestPayload | null }) {
  const equity = backtest?.equity ?? []
  if (!equity.length) return <Empty text="运行回测后显示权益记录" />
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th className="left">日期</th>
          <th>收盘</th>
          <th>现金</th>
          <th>持仓市值</th>
          <th>浮动盈亏</th>
          <th>权益</th>
          <th className="left">持仓网格</th>
        </tr>
      </thead>
      <tbody>
        {equity.slice(-200).map((row, index) => (
          <tr key={`${row.date}-${index}`}>
            <td className="left">{String(row.date).slice(0, 10)}</td>
            <td>{formatNumber(row.close)}</td>
            <td>{formatNumber(row.cash)}</td>
            <td>{formatNumber(row.open_position_value)}</td>
            <td>{formatNumber(row.floating_pnl)}</td>
            <td>{formatNumber(row.total_equity)}</td>
            <td className="left">{row.open_grid_levels || '-'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function ReportPreview({ plan, backtest }: { plan: PlanPayload | null; backtest: BacktestPayload | null }) {
  const lines = [
    '# 页面运行摘要',
    '',
    `计划网格数: ${plan?.levels.length ?? 0}`,
    `回测交易数: ${backtest?.trades.length ?? 0}`,
    `警告: ${[...(plan?.warnings ?? []), ...(backtest?.warnings ?? [])].join('; ') || '-'}`,
  ]
  return <pre className="report-preview">{lines.join('\n')}</pre>
}

function Empty({ text }: { text: string }) {
  return <div className="empty-state">{text}</div>
}
