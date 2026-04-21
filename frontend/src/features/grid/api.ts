import type {
  ApiResponse,
  BacktestPayload,
  GridConfig,
  HistoryPayload,
  PlanPayload,
} from './types'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  const payload = (await response.json()) as ApiResponse<T>
  if (!payload.ok || !payload.data) {
    throw new Error(payload.errors.join('; ') || '请求失败')
  }
  return payload.data
}

export function fetchHistory(config: GridConfig) {
  return postJson<HistoryPayload>('/api/grid/v1/history', {
    symbol: config.symbol,
    start_date: config.start_date || null,
    end_date: config.end_date || null,
    adjust_method: config.adjust_method,
  })
}

export function generatePlan(config: GridConfig) {
  return postJson<PlanPayload>('/api/grid/v1/plan', config)
}

export function runBacktest(config: GridConfig) {
  return postJson<BacktestPayload>('/api/grid/v1/backtest', { config })
}

