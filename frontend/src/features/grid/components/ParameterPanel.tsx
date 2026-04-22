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

  const updateStrategyVersion = (strategyVersion: GridConfig['strategy_version']) => {
    const useScaling = strategyVersion === '2.2' || strategyVersion === '2.3'
    onChange({
      ...config,
      strategy_version: strategyVersion,
      amount_mode: useScaling && config.amount_mode === 'equal' ? 'arithmetic' : config.amount_mode,
      retain_profit: {
        ...config.retain_profit,
        enabled: strategyVersion !== '1.0',
      },
    })
  }

  const updateRetainProfit = (value: Partial<GridConfig['retain_profit']>) => {
    onChange({ ...config, retain_profit: { ...config.retain_profit, ...value } })
  }

  const updateSubGrid = (index: number, value: Partial<GridConfig['sub_grids'][number]>) => {
    const subGrids = config.sub_grids.map((item, itemIndex) =>
      itemIndex === index ? { ...item, ...value } : item,
    )
    onChange({ ...config, sub_grids: subGrids })
  }

  const updateSubGridRetainProfit = (
    index: number,
    value: Partial<GridConfig['sub_grids'][number]['retain_profit']>,
  ) => {
    const subGrids = config.sub_grids.map((item, itemIndex) =>
      itemIndex === index ? { ...item, retain_profit: { ...item.retain_profit, ...value } } : item,
    )
    onChange({ ...config, sub_grids: subGrids })
  }

  const numberInput = (key: FieldKey, label: string, step = '0.001', disabled = false) => (
    <div className="field">
      <label>{label}</label>
      <input
        type="number"
        step={step}
        disabled={disabled}
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
          <span>Grid {config.strategy_version}</span>
        </div>
      </div>

      <section className="section">
        <h3>标的与区间</h3>
        <div className="field-grid">
          <div className="field">
            <label>策略版本</label>
            <select
              value={config.strategy_version}
              onChange={(event) => updateStrategyVersion(event.target.value as GridConfig['strategy_version'])}
            >
              <option value="1.0">1.0 基础网格</option>
              <option value="2.1">2.1 留利润</option>
              <option value="2.2">2.2 加码增强</option>
              <option value="2.3">2.3 一网打尽</option>
            </select>
          </div>
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
              <option value="none">不复权</option>
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
        <div className="section-actions">
          <button className="button" onClick={onLoadHistory} disabled={busy}>
            加载行情
          </button>
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
          {numberInput('first_price', '首网价格', '0.001', config.first_price_mode !== 'fixed')}
          {numberInput(
            'high_drawdown_pct',
            '高点回撤比例',
            '0.01',
            config.first_price_mode !== 'drawdown_from_high',
          )}
        </div>
      </section>

      <section className="section">
        <h3>网格与底部</h3>
        <div className="field-grid">
          {numberInput('grid_pct', '网格比例', '0.01')}
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
          {numberInput('bottom_price', '底部价格', '0.001', config.bottom_mode !== 'fixed')}
          {numberInput(
            'bottom_drawdown_pct',
            '首网回撤比例',
            '0.01',
            config.bottom_mode !== 'drawdown_from_first',
          )}
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
              <option value="geometric">等比递增</option>
            </select>
          </div>
          {numberInput('scale_start_level', '开始加码格', '1')}
          {numberInput('amount_step', '递增金额', '100', config.amount_mode !== 'arithmetic')}
          {numberInput('amount_ratio', '递增倍率', '0.01', config.amount_mode !== 'geometric')}
          {config.strategy_version !== '1.0' && (
            <>
              <div className="field">
                <label>留利润</label>
                <label className="check-field">
                  <input
                    type="checkbox"
                    checked={config.retain_profit.enabled}
                    onChange={(event) => updateRetainProfit({ enabled: event.target.checked })}
                  />
                  <span>启用</span>
                </label>
              </div>
              <div className="field">
                <label>留利润倍数</label>
                <input
                  type="number"
                  step="1"
                  min="1"
                  disabled={!config.retain_profit.enabled}
                  value={config.retain_profit.multiplier}
                  onChange={(event) => updateRetainProfit({ multiplier: Number(event.target.value) })}
                />
              </div>
            </>
          )}
          {config.strategy_version === '2.3' && (
            <div className="field full">
              <label>子网格</label>
              <div className="subgrid-list">
                {config.sub_grids.map((subGrid, index) => (
                  <details className="subgrid-item" key={subGrid.grid_name} open={index === 0}>
                    <summary className="subgrid-header">
                      <span className="subgrid-summary-title">{subGrid.grid_name}</span>
                      <span className="subgrid-summary-text">
                        {formatPctLabel(subGrid.grid_pct)} / {formatAmountLabel(subGrid.first_amount)} /{' '}
                        {amountModeLabel(subGrid.amount_mode)} / 起始格{subGrid.price_start_level}
                      </span>
                      <label className="check-field">
                        <input
                          type="checkbox"
                          checked={subGrid.enabled}
                          onChange={(event) => updateSubGrid(index, { enabled: event.target.checked })}
                        />
                        <span>启用</span>
                      </label>
                    </summary>
                    <div className="subgrid-fields">
                      <div className="field">
                        <label>网格比例</label>
                        <input
                          type="number"
                          step="0.01"
                          value={subGrid.grid_pct}
                          onChange={(event) => updateSubGrid(index, { grid_pct: Number(event.target.value) })}
                        />
                      </div>
                      <div className="field">
                        <label>投入金额</label>
                        <input
                          type="number"
                          step="100"
                          value={subGrid.first_amount}
                          onChange={(event) => updateSubGrid(index, { first_amount: Number(event.target.value) })}
                        />
                      </div>
                      <div className="field">
                        <label>投入模式</label>
                        <select
                          value={subGrid.amount_mode}
                          onChange={(event) =>
                            updateSubGrid(index, { amount_mode: event.target.value as GridConfig['amount_mode'] })
                          }
                        >
                          <option value="equal">每网等额</option>
                          <option value="arithmetic">等差递增</option>
                          <option value="geometric">等比递增</option>
                        </select>
                      </div>
                      <div className="field">
                        <label>价格起始格</label>
                        <input
                          type="number"
                          step="1"
                          value={subGrid.price_start_level}
                          onChange={(event) => updateSubGrid(index, { price_start_level: Number(event.target.value) })}
                        />
                      </div>
                      {subGrid.amount_mode !== 'equal' && (
                        <div className="field">
                          <label>开始加码格</label>
                          <input
                            type="number"
                            step="1"
                            value={subGrid.scale_start_level}
                            onChange={(event) =>
                              updateSubGrid(index, { scale_start_level: Number(event.target.value) })
                            }
                          />
                        </div>
                      )}
                      {subGrid.amount_mode === 'arithmetic' && (
                        <div className="field">
                          <label>递增金额</label>
                          <input
                            type="number"
                            step="100"
                            value={subGrid.amount_step}
                            onChange={(event) => updateSubGrid(index, { amount_step: Number(event.target.value) })}
                          />
                        </div>
                      )}
                      {subGrid.amount_mode === 'geometric' && (
                        <div className="field">
                          <label>递增倍率</label>
                          <input
                            type="number"
                            step="0.01"
                            value={subGrid.amount_ratio}
                            onChange={(event) => updateSubGrid(index, { amount_ratio: Number(event.target.value) })}
                          />
                        </div>
                      )}
                      <div className="field">
                        <label>留利润</label>
                        <label className="check-field">
                          <input
                            type="checkbox"
                            checked={subGrid.retain_profit.enabled}
                            onChange={(event) => updateSubGridRetainProfit(index, { enabled: event.target.checked })}
                          />
                          <span>启用</span>
                        </label>
                      </div>
                      <div className="field">
                        <label>留利润倍数</label>
                        <input
                          type="number"
                          step="1"
                          min="1"
                          disabled={!subGrid.retain_profit.enabled}
                          value={subGrid.retain_profit.multiplier}
                          onChange={(event) =>
                            updateSubGridRetainProfit(index, { multiplier: Number(event.target.value) })
                          }
                        />
                      </div>
                    </div>
                  </details>
                ))}
              </div>
            </div>
          )}
          <details className="collapse-block field full">
            <summary>
              <span>交易成本与输出</span>
              <small>
                {config.lot_size}股 / 手续费{config.fee_rate} / 滑点{config.slippage_rate}
              </small>
            </summary>
            <div className="field-grid collapse-fields">
              {numberInput('price_digits', '价格位数', '1')}
              {numberInput('lot_size', '交易单位', '100')}
              {numberInput('fee_rate', '手续费率', '0.0001')}
              {numberInput('min_fee', '最低手续费', '1')}
              {numberInput('slippage_rate', '滑点率', '0.0001')}
              <div className="field">
                <label>输出前缀</label>
                <input value={config.basename} onChange={(event) => update('basename', event.target.value)} />
              </div>
            </div>
          </details>
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

function amountModeLabel(value: GridConfig['amount_mode']) {
  if (value === 'arithmetic') return '等差'
  if (value === 'geometric') return '等比'
  return '等额'
}

function formatPctLabel(value: number) {
  return `${(value * 100).toFixed(0)}%`
}

function formatAmountLabel(value: number) {
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(value)
}
