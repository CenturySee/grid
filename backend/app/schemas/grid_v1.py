from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


AdjustMethod = Literal["none", "forward", "backward"]


class GridV1Config(BaseModel):
    symbol: str = "sh510300"
    first_price_mode: Literal["fixed", "drawdown_from_high"] = "fixed"
    first_price: float | None = 4.0
    high_drawdown_pct: float | None = 0.2
    start_date: str | None = None
    end_date: str | None = None
    adjust_method: AdjustMethod = "forward"
    grid_pct: float = 0.05
    bottom_mode: Literal["fixed", "drawdown_from_first"] = "fixed"
    bottom_price: float | None = 3.0
    bottom_drawdown_pct: float | None = 0.4
    first_amount: float = 10000.0
    amount_mode: Literal["equal", "arithmetic"] = "arithmetic"
    amount_step: float = 500.0
    lot_size: int = 100
    fee_rate: float = 0.0002
    min_fee: float = 5.0
    slippage_rate: float = 0.0005
    price_digits: int = 3
    basename: str = "grid_v1"


class HistoryRequest(BaseModel):
    symbol: str = "sh510300"
    start_date: str | None = None
    end_date: str | None = None
    adjust_method: AdjustMethod = "forward"


class BacktestRequest(BaseModel):
    config: GridV1Config = Field(default_factory=GridV1Config)
    initial_cash: float | None = None


class ConfigTextRequest(BaseModel):
    config: GridV1Config = Field(default_factory=GridV1Config)


JsonDict = dict[str, Any]
