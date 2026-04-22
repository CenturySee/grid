import { useEffect, useMemo, useRef, useState } from 'react'
import * as echarts from 'echarts'
import type { BacktestPayload, EquityRecord, GridLevel, PlanPayload, TradeRecord } from '../types'
import { formatNumber, formatPct } from '../utils'

type Props = {
  plan: PlanPayload | null
  backtest: BacktestPayload | null
}

const tabs = ['网格计划', '压力测试', '回测指标', '交易记录', '权益曲线', '权益明细', '报告'] as const
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
        {active === '权益曲线' && <EquityChartPanel backtest={backtest} />}
        {active === '权益明细' && <EquityTable backtest={backtest} />}
        {active === '报告' && <ReportPreview plan={plan} backtest={backtest} />}
      </div>
    </section>
  )
}

function PlanTable({ levels }: { levels: GridLevel[] }) {
  if (!levels.length) return <Empty text="生成计划后显示网格明细" />
  return (
    <div className="table-wrap limited">
      <table className="data-table">
        <thead>
          <tr>
            <th>网格</th>
            <th>子网格</th>
            <th>买入价</th>
            <th>卖出价</th>
            <th>计划金额</th>
            <th>份额</th>
            <th>实际投入</th>
            <th>预期利润</th>
            <th>预估留存</th>
            <th>累计资金</th>
            <th className="left">提示</th>
          </tr>
        </thead>
        <tbody>
          {levels.map((level) => (
            <tr key={level.level_index}>
              <td>{level.level_index}</td>
              <td>{level.grid_name ?? '-'}</td>
              <td>{formatNumber(level.buy_price)}</td>
              <td>{formatNumber(level.sell_price)}</td>
              <td>{formatNumber(level.planned_amount)}</td>
              <td>{formatNumber(level.shares, 0)}</td>
              <td>{formatNumber(level.actual_invested)}</td>
              <td>{formatNumber(level.expected_profit)}</td>
              <td>{formatNumber(level.expected_retained_shares ?? 0, 0)}</td>
              <td>{formatNumber(level.cumulative_cost)}</td>
              <td className="left">{level.warning || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SummaryView({ summary }: { summary: Record<string, unknown> | null }) {
  if (!summary) return <Empty text="运行后显示摘要指标" />
  const items: Array<[string, unknown, 'number' | 'pct' | 'text']> = [
    ['策略版本', summary.strategy_version, 'text'],
    ['留利润', summary.retain_profit_enabled, 'text'],
    ['最大资金占用', summary.max_capital_required ?? summary.max_capital_in_use, 'number'],
    ['底部浮亏', summary.floating_pnl_at_bottom ?? summary.max_floating_loss, 'number'],
    ['最大回撤', summary.max_drawdown, 'pct'],
    ['总收益率', summary.total_return, 'pct'],
    ['买入次数', summary.buy_count, 'text'],
    ['卖出次数', summary.sell_count, 'text'],
    ['留存市值', summary.retained_value, 'number'],
    ['留存份额', summary.retained_shares, 'text'],
    ['留存贡献', summary.retained_position_contribution, 'number'],
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
    <div className="table-wrap limited">
      <table className="data-table">
        <thead>
          <tr>
            <th className="left">日期</th>
            <th>动作</th>
            <th>网格</th>
            <th>子网格</th>
            <th>计划价</th>
            <th>成交价</th>
            <th>份额</th>
            <th>留存</th>
            <th>卖出模式</th>
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
              <td>{trade.grid_name ?? '-'}</td>
              <td>{formatNumber(trade.plan_price)}</td>
              <td>{formatNumber(trade.exec_price)}</td>
              <td>{formatNumber(trade.shares, 0)}</td>
              <td>{formatNumber(trade.retained_shares, 0)}</td>
              <td>{trade.sell_mode || '-'}</td>
              <td>{formatNumber(trade.net_amount)}</td>
              <td>{formatNumber(trade.realized_pnl)}</td>
              <td>{trade.trigger_type}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function EquityChartPanel({ backtest }: { backtest: BacktestPayload | null }) {
  const equity = backtest?.equity ?? []
  if (!equity.length) return <Empty text="运行回测后显示权益曲线" />
  return (
    <div className="equity-chart-view">
      <EquityCurve equity={equity} />
    </div>
  )
}

function EquityTable({ backtest }: { backtest: BacktestPayload | null }) {
  const equity = backtest?.equity ?? []
  if (!equity.length) return <Empty text="运行回测后显示权益明细" />
  return (
    <div className="table-wrap limited">
      <table className="data-table">
        <thead>
          <tr>
            <th className="left">日期</th>
            <th>收盘</th>
            <th>现金</th>
            <th>持仓市值</th>
            <th>留存市值</th>
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
              <td>{formatNumber(row.retained_value)}</td>
              <td>{formatNumber(row.floating_pnl)}</td>
              <td>{formatNumber(row.total_equity)}</td>
              <td className="left">{row.open_grid_levels || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function EquityCurve({ equity }: { equity: EquityRecord[] }) {
  const ref = useRef<HTMLDivElement | null>(null)
  const option = useMemo(() => {
    const rows = equity
      .map((row) => ({
        date: String(row.date).slice(0, 10),
        totalEquity: toNumber(row.total_equity),
      }))
      .filter((row): row is { date: string; totalEquity: number } => row.totalEquity !== null)

    const firstEquity = rows[0]?.totalEquity ?? 0
    const netValues = rows.map((row) => (firstEquity > 0 ? row.totalEquity / firstEquity : 0))
    let peak = Number.NEGATIVE_INFINITY
    const drawdowns = rows.map((row) => {
      peak = Math.max(peak, row.totalEquity)
      return peak > 0 ? row.totalEquity / peak - 1 : 0
    })

    return {
      animation: false,
      grid: { left: 66, right: 58, top: 30, bottom: 48 },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (value: unknown) => formatNumber(value),
      },
      legend: { top: 0, data: ['净值曲线', '最大回撤曲线'] },
      xAxis: {
        type: 'category',
        data: rows.map((row) => row.date),
        axisLabel: { color: '#68707d' },
      },
      yAxis: [
        {
          type: 'value',
          scale: true,
          axisLabel: { color: '#68707d' },
          splitLine: { lineStyle: { color: '#edf0f2' } },
        },
        {
          type: 'value',
          axisLabel: { color: '#68707d', formatter: (value: number) => `${(value * 100).toFixed(0)}%` },
          splitLine: { show: false },
        },
      ],
      dataZoom: [
        { type: 'inside', start: 0, end: 100 },
        { type: 'slider', height: 18, bottom: 16, start: 0, end: 100 },
      ],
      series: [
        {
          name: '净值曲线',
          type: 'line',
          smooth: true,
          showSymbol: false,
          data: netValues,
          lineStyle: { color: '#3267d6', width: 2 },
          itemStyle: { color: '#3267d6' },
        },
        {
          name: '最大回撤曲线',
          type: 'line',
          yAxisIndex: 1,
          smooth: true,
          showSymbol: false,
          data: drawdowns,
          lineStyle: { color: '#c2410c', width: 2 },
          areaStyle: { color: 'rgba(194, 65, 12, 0.1)' },
          itemStyle: { color: '#c2410c' },
          tooltip: { valueFormatter: (value: number) => formatPct(value) },
        },
      ],
    }
  }, [equity])

  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    chart.setOption(option, true)
    const resize = () => chart.resize()
    window.addEventListener('resize', resize)
    return () => {
      window.removeEventListener('resize', resize)
      chart.dispose()
    }
  }, [option])

  return <div ref={ref} className="equity-chart" />
}

function toNumber(value: unknown): number | null {
  if (typeof value !== 'number' || Number.isNaN(value)) return null
  return value
}

function getSummaryNumber(summary: Record<string, unknown> | null | undefined, key: string) {
  const value = summary?.[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function conclusionLines(plan: PlanPayload | null, backtest: BacktestPayload | null) {
  const summary = backtest?.summary ?? null
  const totalReturn = getSummaryNumber(summary, 'total_return')
  const maxDrawdown = getSummaryNumber(summary, 'max_drawdown')
  const maxCapital = getSummaryNumber(summary, 'max_capital_in_use')
  const finalEquity = getSummaryNumber(summary, 'final_equity')
  const openLotCount = getSummaryNumber(summary, 'open_lot_count')
  const buyCount = getSummaryNumber(summary, 'buy_count')
  const sellCount = getSummaryNumber(summary, 'sell_count')
  const retainedValue = getSummaryNumber(summary, 'retained_value')
  const warnings = [...(plan?.warnings ?? []), ...(backtest?.warnings ?? [])]

  if (!backtest) {
    return [
      '当前还没有回测结果，报告只包含计划层面的信息。',
      `计划网格数为 ${plan?.levels.length ?? 0} 个，生成回测后可补充收益、回撤和交易活跃度结论。`,
    ]
  }

  return [
    `本次回测期末权益为 ${formatNumber(finalEquity)}，总收益率 ${formatPct(totalReturn)}，最大回撤 ${formatPct(maxDrawdown)}。`,
    `最大资金占用约 ${formatNumber(maxCapital)}，买入 ${formatNumber(buyCount, 0)} 次，卖出 ${formatNumber(sellCount, 0)} 次。`,
    retainedValue && retainedValue > 0
      ? `留利润仓位期末市值约 ${formatNumber(retainedValue)}，这部分已计入期末权益。`
      : '本次回测没有形成留利润仓位。',
    openLotCount && openLotCount > 0
      ? `期末仍有 ${formatNumber(openLotCount, 0)} 个未平仓网格，后续表现对标的价格继续下行较敏感。`
      : '期末没有未平仓网格，回测区间内触发仓位已经完成闭环。',
    warnings.length ? `需要关注的提示：${warnings.join('; ')}` : '计划和回测没有返回额外警告。',
  ]
}

function ReportPreview({ plan, backtest }: { plan: PlanPayload | null; backtest: BacktestPayload | null }) {
  const lines = [
    '# 页面运行摘要',
    '',
    '## 总结结论',
    '',
    ...conclusionLines(plan, backtest).map((line) => `- ${line}`),
    '',
    '## 核心数据',
    '',
    `计划网格数: ${plan?.levels.length ?? 0}`,
    `策略版本: ${backtest?.summary?.strategy_version ?? plan?.config?.strategy_version ?? '-'}`,
    `留利润: ${formatMetricValue(backtest?.summary?.retain_profit_enabled, 'text')}`,
    `回测交易数: ${backtest?.trades.length ?? 0}`,
    `最大资金占用: ${formatNumber(
      backtest?.summary?.max_capital_in_use ?? plan?.summary?.max_capital_required,
    )}`,
    `留存市值: ${formatNumber(backtest?.summary?.retained_value)}`,
    `期末权益: ${formatNumber(backtest?.summary?.final_equity)}`,
    `总收益率: ${formatPct(backtest?.summary?.total_return)}`,
    `最大回撤: ${formatPct(backtest?.summary?.max_drawdown)}`,
    `警告: ${[...(plan?.warnings ?? []), ...(backtest?.warnings ?? [])].join('; ') || '-'}`,
  ]
  return <pre className="report-preview">{lines.join('\n')}</pre>
}

function Empty({ text }: { text: string }) {
  return <div className="empty-state">{text}</div>
}
