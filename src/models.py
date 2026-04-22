from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FirstPriceMode(str, Enum):
    FIXED = "fixed"
    DRAWDOWN_FROM_HIGH = "drawdown_from_high"


class BottomMode(str, Enum):
    FIXED = "fixed"
    DRAWDOWN_FROM_FIRST = "drawdown_from_first"


class AmountMode(str, Enum):
    EQUAL = "equal"
    ARITHMETIC = "arithmetic"
    GEOMETRIC = "geometric"


@dataclass(frozen=True)
class RetainProfitConfig:
    enabled: bool = False
    multiplier: float = 1.0


@dataclass(frozen=True)
class PriceContext:
    source: str = "manual"
    adjusted: bool = False
    adjust_method: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    period_high: float | None = None
    period_low: float | None = None
    latest_close: float | None = None
    first_price_close_percentile: float | None = None
    close_below_first_days: int | None = None
    close_below_first_pct: float | None = None
    low_touch_first_days: int | None = None
    low_touch_first_pct: float | None = None
    drawdown_from_period_high_pct: float | None = None


@dataclass(frozen=True)
class GridPlanConfig:
    symbol: str | None
    first_price: float
    grid_pct: float
    bottom_price: float
    first_amount: float
    grid_name: str = "default"
    strategy_version: str = "1.0"
    amount_mode: AmountMode = AmountMode.EQUAL
    amount_step: float = 0.0
    amount_ratio: float = 1.0
    scale_start_level: int = 1
    price_start_level: int = 1
    retain_profit: RetainProfitConfig = field(default_factory=RetainProfitConfig)
    lot_size: int = 100
    fee_rate: float = 0.0
    min_fee: float = 0.0
    slippage_rate: float = 0.0
    price_digits: int = 4


@dataclass(frozen=True)
class GridLevel:
    grid_name: str
    level_index: int
    buy_price: float
    sell_price: float
    grid_step: float
    planned_amount: float
    shares: int
    actual_invested: float
    unused_amount: float
    amount_usage_pct: float
    buy_fee: float
    total_cost: float
    gross_sell_amount: float
    sell_fee: float
    net_sell_amount: float
    expected_profit: float
    expected_return_pct: float
    expected_sold_shares: int
    expected_retained_shares: int
    expected_retained_value: float
    expected_recover_cost: float
    expected_sell_mode: str
    cumulative_cost: float
    drawdown_from_first_pct: float
    covers_bottom: bool
    warning: str


@dataclass(frozen=True)
class StressSummary:
    symbol: str | None
    first_price: float
    bottom_price: float
    grid_pct: float
    grid_step: float
    grid_count: int
    max_capital_required: float
    total_shares_at_bottom: int
    average_cost: float
    market_value_at_bottom: float
    floating_pnl_at_bottom: float
    floating_pnl_pct_at_bottom: float
    last_buy_price: float
    covers_bottom: bool
    bottom_over_coverage: float
    total_planned_amount: float
    total_actual_invested: float
    total_unused_amount: float
    zero_share_levels: int
    warning_count: int


@dataclass(frozen=True)
class GridPlan:
    config: GridPlanConfig
    levels: list[GridLevel]
    summary: StressSummary
    price_context: PriceContext | None = None
    warnings: list[str] | None = None
