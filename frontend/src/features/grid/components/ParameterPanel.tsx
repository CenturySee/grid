import type { GridConfig } from '../types'
import { normalizeDate, parseNullableNumber } from '../utils'

type Props = {
  config: GridConfig
  busy: boolean
  validations: string[]
  onChange: (config: GridConfig) => void
  onLoadHistory: () => void
  onGeneratePlan: () => void
  onRunBacktest: () => void
}

type FieldKey = keyof GridConfig

export function ParameterPanel({
  config,
  busy,
  validations,
  onChange,
  onLoadHistory,
  onGeneratePlan,
  onRunBacktest,
}: Props) {
  const update = <K extends FieldKey>(key: K, value: GridConfig[K]) => {
    onChange({ ...config, [key]: value })
  }

  const numberInput = (key: FieldKey, label: string, step = '0.001') => (
    <div className="field">
      <label>{label}</label>
      <input
        type="number"
        step={step}
        value={(config[key] as number | null) ?? ''}
        onChange={(event) => update(key, parseNullableNumber(event.target.value) as never)}
      />
    </div>
  )

  return (
    <aside className="panel parameter-panel">
      <div className="panel-header">
        <div className="panel-title">
          <h2>参数配置</h2>
          <span>Grid v1</span>
        </div>
      </div>

      <section className="section">
        <h3>标的与区间</h3>
        <div className="field-grid">
          <div className="field">
            <label>标的代码</label>
            <input value={config.symbol} onChange={(event) => update('symbol', event.target.value)} />
          </div>
          <div className="field">
            <label>复权方式</label>
            <select
              value={config.adjust_method}
              onChange={(event) => update('adjust_method', event.target.value as GridConfig['adjust_method'])}
            >
              <option value="forward">前复权</option>
              <option value="backward">后复权</option>
            </select>
          </div>
          <div className="field">
            <label>起始日期</label>
            <input
              type="date"
              value={normalizeDate(config.start_date)}
              onChange={(event) => update('start_date', event.target.value || null)}
            />
          </div>
          <div className="field">
            <label>结束日期</label>
            <input
              type="date"
              value={normalizeDate(config.end_date)}
              onChange={(event) => update('end_date', event.target.value || null)}
            />
          </div>
        </div>
      </section>

      <section className="section">
        <h3>首网设置</h3>
        <div className="field-grid">
          <div className="field full">
            <label>首网模式</label>
            <select
              value={config.first_price_mode}
              onChange={(event) => update('first_price_mode', event.target.value as GridConfig['first_price_mode'])}
            >
              <option value="fixed">固定点位</option>
              <option value="drawdown_from_high">距高点回撤</option>
            </select>
          </div>
          {numberInput('first_price', '首网价格', '0.001')}
          {numberInput('high_drawdown_pct', '高点回撤比例', '0.01')}
        </div>
      </section>

      <section className="section">
        <h3>网格与底部</h3>
        <div className="field-grid">
          {numberInput('grid_pct', '网格比例', '0.01')}
          {numberInput('price_digits', '价格位数', '1')}
          <div className="field full">
            <label>底部模式</label>
            <select
              value={config.bottom_mode}
              onChange={(event) => update('bottom_mode', event.target.value as GridConfig['bottom_mode'])}
            >
              <option value="fixed">固定底部</option>
              <option value="drawdown_from_first">距首网回撤</option>
            </select>
          </div>
          {numberInput('bottom_price', '底部价格', '0.001')}
          {numberInput('bottom_drawdown_pct', '首网回撤比例', '0.01')}
        </div>
      </section>

      <section className="section">
        <h3>资金与成本</h3>
        <div className="field-grid">
          {numberInput('first_amount', '首网投入', '100')}
          <div className="field">
            <label>投入模式</label>
            <select
              value={config.amount_mode}
              onChange={(event) => update('amount_mode', event.target.value as GridConfig['amount_mode'])}
            >
              <option value="equal">每网等额</option>
              <option value="arithmetic">等差递增</option>
            </select>
          </div>
          {numberInput('amount_step', '递增金额', '100')}
          {numberInput('lot_size', '交易单位', '100')}
          {numberInput('fee_rate', '手续费率', '0.0001')}
          {numberInput('min_fee', '最低手续费', '1')}
          {numberInput('slippage_rate', '滑点率', '0.0001')}
          <div className="field">
            <label>输出前缀</label>
            <input value={config.basename} onChange={(event) => update('basename', event.target.value)} />
          </div>
        </div>
        {validations.length > 0 && (
          <div className="validation-list">
            {validations.map((item) => (
              <div className="validation-item" key={item}>
                {item}
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="actions">
        <button className="button" onClick={onLoadHistory} disabled={busy}>
          加载行情
        </button>
        <button className="button primary" onClick={onGeneratePlan} disabled={busy || validations.length > 0}>
          生成计划
        </button>
        <button className="button" onClick={onRunBacktest} disabled={busy || validations.length > 0}>
          运行回测
        </button>
      </div>
    </aside>
  )
}

