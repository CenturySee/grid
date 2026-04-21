import { useEffect, useMemo, useRef } from 'react'
import * as echarts from 'echarts'
import type { BacktestPayload, GridLevel, HistoryRecord } from '../types'

type Props = {
  history: HistoryRecord[]
  levels: GridLevel[]
  backtest: BacktestPayload | null
}

export function KlineChart({ history, levels, backtest }: Props) {
  const ref = useRef<HTMLDivElement | null>(null)
  const option = useMemo(() => buildOption(history, levels, backtest), [history, levels, backtest])

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

  return <div ref={ref} className="chart" />
}

function buildOption(history: HistoryRecord[], levels: GridLevel[], backtest: BacktestPayload | null) {
  const dates = history.map((item) => item.date)
  const candles = history.map((item) => [item.open, item.close, item.low, item.high])
  const buyLines = levels.map((level) => ({
    yAxis: level.buy_price,
    lineStyle: { color: '#5c7cfa', opacity: 0.36, type: 'dashed' },
    label: { formatter: `B${level.level_index} ${level.buy_price.toFixed(3)}`, color: '#5c7cfa' },
  }))
  const sellLines = levels.map((level) => ({
    yAxis: level.sell_price,
    lineStyle: { color: '#f08c00', opacity: 0.24, type: 'dotted' },
    label: { formatter: `S${level.level_index} ${level.sell_price.toFixed(3)}`, color: '#f08c00' },
  }))
  const trades = backtest?.trades ?? []
  const buyPoints = trades
    .filter((trade) => trade.action === 'buy')
    .map((trade) => [trade.date, trade.exec_price])
  const sellPoints = trades
    .filter((trade) => trade.action === 'sell')
    .map((trade) => [trade.date, trade.exec_price])

  return {
    animation: false,
    grid: { left: 58, right: 24, top: 26, bottom: 58 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: true,
      axisLine: { lineStyle: { color: '#c9d0d8' } },
      axisLabel: { color: '#68707d' },
    },
    yAxis: {
      scale: true,
      axisLine: { lineStyle: { color: '#c9d0d8' } },
      splitLine: { lineStyle: { color: '#edf0f2' } },
      axisLabel: { color: '#68707d' },
    },
    dataZoom: [
      { type: 'inside', start: 65, end: 100 },
      { type: 'slider', height: 22, bottom: 18, start: 65, end: 100 },
    ],
    series: [
      {
        name: '日K',
        type: 'candlestick',
        data: candles,
        itemStyle: {
          color: '#d94841',
          color0: '#2f9e44',
          borderColor: '#d94841',
          borderColor0: '#2f9e44',
        },
        markLine: {
          symbol: ['none', 'none'],
          silent: true,
          data: [...buyLines, ...sellLines],
        },
      },
      {
        name: '买入',
        type: 'scatter',
        symbol: 'triangle',
        symbolSize: 9,
        itemStyle: { color: '#2f9e44' },
        data: buyPoints,
      },
      {
        name: '卖出',
        type: 'scatter',
        symbol: 'diamond',
        symbolSize: 9,
        itemStyle: { color: '#d94841' },
        data: sellPoints,
      },
    ],
  }
}

