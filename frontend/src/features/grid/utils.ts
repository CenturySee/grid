export function formatNumber(value: unknown, digits = 3): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return value == null ? '-' : String(value)
  return new Intl.NumberFormat('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value)
}

export function formatPct(value: unknown, digits = 2): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-'
  return `${(value * 100).toFixed(digits)}%`
}

export function normalizeDate(value: string | null): string {
  return value ?? ''
}

export function parseNullableNumber(value: string): number | null {
  if (value.trim() === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}
