from __future__ import annotations

from argparse import Namespace
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.backtest_v1 import run_grid_v1_backtest
from src.config_loader import load_config_file
from src.data_loader import build_price_context, filter_history, load_adjusted_daily_history
from src.grid_plan import build_grid_plan
from src.models import AmountMode, BottomMode, FirstPriceMode, GridPlanConfig

from backend.app.schemas.grid_v1 import GridV1Config


def normalize_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if hasattr(value, "isoformat") and value.__class__.__name__ in {"date", "datetime"}:
        return value.isoformat()
    if is_dataclass(value):
        return normalize_value(asdict(value))
    if isinstance(value, dict):
        return {key: normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    return value


def dataframe_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return normalize_value(frame.to_dict(orient="records"))


def load_history_records(symbol: str, start_date: str | None, end_date: str | None, adjust_method: str) -> dict[str, Any]:
    history = load_adjusted_daily_history(symbol, adjust_method=adjust_method)
    history = filter_history(history, start_date=start_date, end_date=end_date)
    columns = ["date", "open", "high", "low", "close"]
    if "volume" in history.columns:
        columns.append("volume")
    elif "vol" in history.columns:
        history = history.rename(columns={"vol": "volume"})
        columns.append("volume")
    records = history[columns].copy()
    for col in ("open", "high", "low", "close"):
        records[col] = records[col].round(3)
    return {
        "symbol": symbol,
        "adjust_method": adjust_method,
        "records": dataframe_records(records),
    }


def namespace_from_config(config: GridV1Config) -> Namespace:
    return Namespace(**config.model_dump())


def resolve_first_price(args: Namespace, history: pd.DataFrame) -> float:
    mode = FirstPriceMode(args.first_price_mode)
    if mode == FirstPriceMode.FIXED:
        if args.first_price is None:
            raise ValueError("first_price is required when first_price_mode is fixed.")
        return float(args.first_price)
    if mode == FirstPriceMode.DRAWDOWN_FROM_HIGH:
        if args.high_drawdown_pct is None:
            raise ValueError("high_drawdown_pct is required when first_price_mode is drawdown_from_high.")
        return float(history["high"].max()) * (1 - args.high_drawdown_pct)
    raise ValueError(f"Unsupported first_price_mode: {mode}")


def resolve_bottom_price(args: Namespace, first_price: float) -> float:
    mode = BottomMode(args.bottom_mode)
    if mode == BottomMode.FIXED:
        if args.bottom_price is None:
            raise ValueError("bottom_price is required when bottom_mode is fixed.")
        return float(args.bottom_price)
    if mode == BottomMode.DRAWDOWN_FROM_FIRST:
        if args.bottom_drawdown_pct is None:
            raise ValueError("bottom_drawdown_pct is required when bottom_mode is drawdown_from_first.")
        return first_price * (1 - args.bottom_drawdown_pct)
    raise ValueError(f"Unsupported bottom_mode: {mode}")


def build_plan_from_config(config: GridV1Config):
    args = namespace_from_config(config)
    history = load_adjusted_daily_history(args.symbol, adjust_method=args.adjust_method)
    history = filter_history(history, start_date=args.start_date, end_date=args.end_date)
    first_price = resolve_first_price(args, history)
    bottom_price = resolve_bottom_price(args, first_price)
    price_context = build_price_context(
        history=history,
        first_price=first_price,
        source="tdx_offline_adjusted",
        adjusted=True,
        adjust_method=args.adjust_method,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    plan_config = GridPlanConfig(
        symbol=args.symbol,
        first_price=first_price,
        grid_pct=args.grid_pct,
        bottom_price=bottom_price,
        first_amount=args.first_amount,
        amount_mode=AmountMode(args.amount_mode),
        amount_step=args.amount_step,
        lot_size=args.lot_size,
        fee_rate=args.fee_rate,
        min_fee=args.min_fee,
        slippage_rate=args.slippage_rate,
        price_digits=args.price_digits,
    )
    return build_grid_plan(plan_config, price_context=price_context), history


def make_plan_payload(config: GridV1Config) -> dict[str, Any]:
    plan, _history = build_plan_from_config(config)
    return {
        "config": normalize_value(asdict(plan.config)),
        "summary": normalize_value(asdict(plan.summary)),
        "price_context": normalize_value(asdict(plan.price_context)) if plan.price_context else None,
        "levels": normalize_value([asdict(level) for level in plan.levels]),
        "warnings": plan.warnings or [],
    }


def make_backtest_payload(config: GridV1Config, initial_cash: float | None = None) -> dict[str, Any]:
    backtest_config = config.model_copy(update={"adjust_method": "forward", "price_digits": 3})
    plan, history = build_plan_from_config(backtest_config)
    trades, equity, days, summary = run_grid_v1_backtest(plan, history, initial_cash=initial_cash)
    return {
        "plan": {
            "summary": normalize_value(asdict(plan.summary)),
            "levels": normalize_value([asdict(level) for level in plan.levels]),
        },
        "summary": dataframe_records(summary)[0] if not summary.empty else {},
        "trades": dataframe_records(trades),
        "equity": dataframe_records(equity),
        "days": dataframe_records(days),
        "warnings": plan.warnings or [],
    }


def load_config_from_path(path: Path) -> GridV1Config:
    return GridV1Config(**load_config_file(path))

