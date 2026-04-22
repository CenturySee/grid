from __future__ import annotations

import argparse
import sys
from argparse import Namespace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backtest_v1 import export_backtest, run_grid_v1_backtest
from src.config_loader import load_config_file
from src.data_loader import build_price_context, filter_history, load_adjusted_daily_history
from src.grid_plan import build_grid_plan, combine_grid_plans
from src.models import AmountMode, BottomMode, FirstPriceMode, GridPlanConfig, RetainProfitConfig


OUTPUT_DIR = PROJECT_ROOT / "outputs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a lightweight daily replay backtest for grid 1.0.")
    parser.add_argument("--config", type=Path, required=True, help="YAML/JSON grid plan config.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--basename", default=None)
    parser.add_argument("--initial-cash", type=float, default=None)
    return parser.parse_args()


def namespace_from_config(config: dict) -> Namespace:
    defaults = {
        "symbol": None,
        "first_price_mode": FirstPriceMode.FIXED.value,
        "first_price": None,
        "high_drawdown_pct": None,
        "start_date": None,
        "end_date": None,
        "adjust_method": "forward",
        "grid_pct": None,
        "bottom_mode": BottomMode.FIXED.value,
        "bottom_price": None,
        "bottom_drawdown_pct": None,
        "first_amount": None,
        "amount_mode": AmountMode.EQUAL.value,
        "amount_step": 0.0,
        "amount_ratio": 1.0,
        "scale_start_level": 1,
        "price_start_level": 1,
        "lot_size": 100,
        "fee_rate": 0.0,
        "min_fee": 0.0,
        "slippage_rate": 0.0,
        "price_digits": 3,
        "basename": None,
        "strategy_version": "1.0",
        "retain_profit_enabled": False,
        "retain_profit_multiplier": 1.0,
    }
    config_items = dict(config)
    sub_grids = config_items.pop("sub_grids", None)
    retain_profit = config_items.pop("retain_profit", None)
    if isinstance(retain_profit, dict):
        config_items.setdefault("retain_profit_enabled", retain_profit.get("enabled", False))
        config_items.setdefault("retain_profit_multiplier", retain_profit.get("multiplier", 1.0))
    merged = defaults | {key.replace("-", "_"): value for key, value in config_items.items()}
    merged["sub_grids"] = sub_grids
    merged["adjust_method"] = "forward"
    if merged["price_digits"] != 3:
        merged["price_digits"] = 3
    required = ("symbol",) if merged.get("strategy_version") == "2.3" and merged.get("sub_grids") else ("symbol", "grid_pct", "first_amount")
    missing = [key for key in required if merged.get(key) is None]
    if missing:
        raise ValueError(f"Missing required config keys: {missing}")
    return Namespace(**merged)


def resolve_first_price(args: Namespace, history) -> float:
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


def build_plan_and_history(config_args: Namespace):
    history = load_adjusted_daily_history(config_args.symbol, adjust_method="forward")
    history = filter_history(history, start_date=config_args.start_date, end_date=config_args.end_date)
    first_price = resolve_first_price(config_args, history)
    bottom_price = resolve_bottom_price(config_args, first_price)
    price_context = build_price_context(
        history=history,
        first_price=first_price,
        source="tdx_offline_qfq",
        adjusted=True,
        adjust_method="forward",
        start_date=config_args.start_date,
        end_date=config_args.end_date,
    )
    base_kwargs = dict(
        symbol=config_args.symbol,
        first_price=first_price,
        bottom_price=bottom_price,
        strategy_version=config_args.strategy_version,
        lot_size=config_args.lot_size,
        fee_rate=config_args.fee_rate,
        min_fee=config_args.min_fee,
        slippage_rate=config_args.slippage_rate,
        price_digits=3,
    )
    if config_args.strategy_version == "2.3" and config_args.sub_grids:
        plans = []
        for sub_grid in config_args.sub_grids:
            if not sub_grid.get("enabled", True):
                continue
            plan_config = GridPlanConfig(
                **base_kwargs,
                grid_name=sub_grid["grid_name"],
                grid_pct=sub_grid["grid_pct"],
                first_amount=sub_grid["first_amount"],
                amount_mode=AmountMode(sub_grid.get("amount_mode", "equal")),
                amount_step=sub_grid.get("amount_step", 0.0),
                amount_ratio=sub_grid.get("amount_ratio", 1.0),
                scale_start_level=sub_grid.get("scale_start_level", 1),
                price_start_level=sub_grid.get("price_start_level", 1),
                retain_profit=RetainProfitConfig(
                    enabled=sub_grid.get("retain_profit", {}).get("enabled", False),
                    multiplier=sub_grid.get("retain_profit", {}).get("multiplier", 1.0),
                ),
            )
            plans.append(build_grid_plan(plan_config, price_context=price_context))
        return combine_grid_plans(plans), history

    plan_config = GridPlanConfig(
        **base_kwargs,
        grid_name="default",
        grid_pct=config_args.grid_pct,
        first_amount=config_args.first_amount,
        amount_mode=AmountMode(config_args.amount_mode),
        amount_step=config_args.amount_step,
        amount_ratio=config_args.amount_ratio,
        scale_start_level=config_args.scale_start_level,
        price_start_level=config_args.price_start_level,
        retain_profit=RetainProfitConfig(
            enabled=config_args.retain_profit_enabled,
            multiplier=config_args.retain_profit_multiplier,
        ),
    )
    return build_grid_plan(plan_config, price_context=price_context), history


def main() -> None:
    cli_args = parse_args()
    config = load_config_file(cli_args.config)
    config_args = namespace_from_config(config)
    plan, history = build_plan_and_history(config_args)
    initial_cash = cli_args.initial_cash if cli_args.initial_cash is not None else plan.summary.max_capital_required
    trades, equity, days, summary = run_grid_v1_backtest(plan, history, initial_cash=initial_cash)
    basename = cli_args.basename or config_args.basename or f"{config_args.symbol}_grid_v1"
    paths = export_backtest(trades, equity, days, summary, cli_args.output_dir, basename)

    row = summary.iloc[0]
    print(f"Grid {config_args.strategy_version} backtest summary")
    print(f"symbol: {row['symbol']}")
    print(f"start_date: {row['start_date']}")
    print(f"end_date: {row['end_date']}")
    print(f"adjust_method: {row['adjust_method']}")
    print(f"initial_cash: {row['initial_cash']:.3f}")
    print(f"final_equity: {row['final_equity']:.3f}")
    print(f"total_return: {row['total_return']:.3%}")
    print(f"realized_pnl: {row['realized_pnl']:.3f}")
    print(f"buy_count: {int(row['buy_count'])}")
    print(f"sell_count: {int(row['sell_count'])}")
    print(f"max_capital_in_use: {row['max_capital_in_use']:.3f}")
    print(f"max_floating_loss: {row['max_floating_loss']:.3f}")
    print(f"max_drawdown: {row['max_drawdown']:.3%}")
    print()
    print(f"trades_csv: {paths[0]}")
    print(f"equity_csv: {paths[1]}")
    print(f"days_csv: {paths[2]}")
    print(f"summary_csv: {paths[3]}")
    print(f"report_md: {paths[4]}")


if __name__ == "__main__":
    main()
