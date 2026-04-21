export type AmountMode = 'equal' | 'arithmetic'
export type FirstPriceMode = 'fixed' | 'drawdown_from_high'
export type BottomMode = 'fixed' | 'drawdown_from_first'

export type GridConfig = {
  symbol: string
  first_price_mode: FirstPriceMode
  first_price: number | null
  high_drawdown_pct: number | null
  start_date: string | null
  end_date: string | null
  adjust_method: 'forward' | 'backward'
  grid_pct: number
  bottom_mode: BottomMode
  bottom_price: number | null
  bottom_drawdown_pct: number | null
  first_amount: number
  amount_mode: AmountMode
  amount_step: number
  lot_size: number
  fee_rate: number
  min_fee: number
  slippage_rate: number
  price_digits: number
  basename: string
}

export type ApiResponse<T> = {
  ok: boolean
  data: T | null
  warnings: string[]
  errors: string[]
}

export type HistoryRecord = {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume?: number
}

export type HistoryPayload = {
  symbol: string
  adjust_method: string
  records: HistoryRecord[]
}

export type GridLevel = {
  level_index: number
  buy_price: number
  sell_price: number
  grid_step: number
  planned_amount: number
  shares: number
  actual_invested: number
  unused_amount: number
  amount_usage_pct: number
  expected_profit: number
  expected_return_pct: number
  cumulative_cost: number
  warning: string
}

export type PlanSummary = Record<string, string | number | boolean | null>

export type PriceContext = Record<string, string | number | boolean | null>

export type PlanPayload = {
  config: GridConfig
  summary: PlanSummary
  price_context: PriceContext | null
  levels: GridLevel[]
  warnings: string[]
}

export type TradeRecord = Record<string, string | number | boolean | null>
export type EquityRecord = Record<string, string | number | boolean | null>
export type DayRecord = Record<string, string | number | boolean | null>

export type BacktestPayload = {
  plan: {
    summary: PlanSummary
    levels: GridLevel[]
  }
  summary: PlanSummary
  trades: TradeRecord[]
  equity: EquityRecord[]
  days: DayRecord[]
  warnings: string[]
}

