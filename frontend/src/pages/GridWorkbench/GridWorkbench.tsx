import { useMemo, useState } from 'react'
import { fetchHistory, generatePlan, runBacktest } from '../../features/grid/api'
import { KlineChart } from '../../features/grid/components/KlineChart'
import { ParameterPanel } from '../../features/grid/components/ParameterPanel'
import { ResultTabs } from '../../features/grid/components/ResultTabs'
import { defaultGridConfig } from '../../features/grid/defaultConfig'
import type { BacktestPayload, GridConfig, HistoryRecord, PlanPayload } from '../../features/grid/types'

export function GridWorkbench() {
  const [config, setConfig] = useState<GridConfig>(defaultGridConfig)
  const [history, setHistory] = useState<HistoryRecord[]>([])
  const [plan, setPlan] = useState<PlanPayload | null>(null)
  const [backtest, setBacktest] = useState<BacktestPayload | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('准备就绪')
  const [error, setError] = useState<string | null>(null)

  const validations = useMemo(() => validateConfig(config), [config])

  const runAction = async (label: string, action: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    setMessage(`${label}中...`)
    try {
      await action()
      setMessage(`${label}完成`)
    } catch (exc) {
      const text = exc instanceof Error ? exc.message : String(exc)
      setError(text)
      setMessage(`${label}失败`)
    } finally {
      setBusy(false)
    }
  }

  const handleLoadHistory = () =>
    runAction('加载行情', async () => {
      const payload = await fetchHistory(config)
      setHistory(payload.records)
    })

  const handleGeneratePlan = () =>
    runAction('生成计划', async () => {
      const [historyPayload, planPayload] = await Promise.all([fetchHistory(config), generatePlan(config)])
      setHistory(historyPayload.records)
      setPlan(planPayload)
      setBacktest(null)
    })

  const handleRunBacktest = () =>
    runAction('运行回测', async () => {
      const [historyPayload, planPayload, backtestPayload] = await Promise.all([
        fetchHistory(config),
        generatePlan(config),
        runBacktest(config),
      ])
      setHistory(historyPayload.records)
      setPlan(planPayload)
      setBacktest(backtestPayload)
    })

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <h1>Grid Strategy Workbench</h1>
          <span>网格 1.0 计划与回测</span>
        </div>
        <div className={`topbar-status ${error ? 'error' : ''}`}>{error ?? message}</div>
      </header>
      <main className="workspace">
        <div className="left-pane">
          <section className="panel chart-panel">
            <div className="panel-header">
              <div className="panel-title">
                <h2>历史日K</h2>
                <span>{config.symbol}</span>
              </div>
              <span>{history.length ? `${history.length} 根K线` : '未加载'}</span>
            </div>
            {history.length ? (
              <KlineChart history={history} levels={plan?.levels ?? []} backtest={backtest} />
            ) : (
              <div className="empty-state">加载行情后显示 K 线、网格线和成交点</div>
            )}
          </section>
          <ResultTabs plan={plan} backtest={backtest} />
        </div>
        <ParameterPanel
          config={config}
          busy={busy}
          validations={validations}
          onChange={setConfig}
          onLoadHistory={handleLoadHistory}
          onGeneratePlan={handleGeneratePlan}
          onRunBacktest={handleRunBacktest}
        />
      </main>
    </div>
  )
}

function validateConfig(config: GridConfig): string[] {
  const items: string[] = []
  if (!config.symbol.trim()) items.push('标的代码不能为空')
  if (config.first_price_mode === 'fixed' && (!config.first_price || config.first_price <= 0)) {
    items.push('固定首网模式下首网价格必须大于 0')
  }
  if (config.first_price_mode === 'drawdown_from_high' && (!config.high_drawdown_pct || config.high_drawdown_pct <= 0)) {
    items.push('距高点回撤模式下回撤比例必须大于 0')
  }
  if (config.grid_pct <= 0 || config.grid_pct >= 1) items.push('网格比例必须在 0 到 1 之间')
  if (config.bottom_mode === 'fixed' && (!config.bottom_price || config.bottom_price <= 0)) {
    items.push('固定底部模式下底部价格必须大于 0')
  }
  if (
    config.bottom_mode === 'fixed' &&
    config.first_price_mode === 'fixed' &&
    config.first_price &&
    config.bottom_price &&
    config.bottom_price >= config.first_price
  ) {
    items.push('底部价格必须低于首网价格')
  }
  if (config.first_amount <= 0) items.push('首网投入金额必须大于 0')
  if (config.lot_size <= 0) items.push('交易单位必须大于 0')
  if (config.start_date && config.end_date && config.start_date > config.end_date) {
    items.push('起始日期不能晚于结束日期')
  }
  return items
}

