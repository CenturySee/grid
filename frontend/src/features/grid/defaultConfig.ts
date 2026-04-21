import type { GridConfig } from './types'

export const defaultGridConfig: GridConfig = {
  symbol: 'sh510300',
  first_price_mode: 'fixed',
  first_price: 4,
  high_drawdown_pct: 0.2,
  start_date: null,
  end_date: null,
  adjust_method: 'forward',
  grid_pct: 0.05,
  bottom_mode: 'fixed',
  bottom_price: 3,
  bottom_drawdown_pct: 0.4,
  first_amount: 10000,
  amount_mode: 'arithmetic',
  amount_step: 500,
  lot_size: 100,
  fee_rate: 0.0002,
  min_fee: 5,
  slippage_rate: 0.0005,
  price_digits: 3,
  basename: 'sample_config_v1',
}

