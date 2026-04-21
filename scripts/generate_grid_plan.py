from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_loader import build_price_context, filter_history, load_adjusted_daily_history
from src.config_loader import load_config_file
from src.grid_plan import build_grid_plan, export_plan, plan_to_frame
from src.models import AmountMode, BottomMode, FirstPriceMode, GridPlanConfig, PriceContext


OUTPUT_DIR = PROJECT_ROOT / "outputs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a grid strategy plan and stress test table.")
    parser.add_argument("--config", type=Path, default=None, help="JSON/YAML config file. CLI values override config.")
    parser.add_argument("--symbol", default=None, help="Symbol such as sh510300 or sz159915.")
    parser.add_argument(
        "--first-price-mode",
        choices=[item.value for item in FirstPriceMode],
        default=FirstPriceMode.FIXED.value,
    )
    parser.add_argument("--first-price", type=float, default=None, help="First grid buy price for fixed mode.")
    parser.add_argument("--high-drawdown-pct", type=float, default=None, help="First price = period high * (1 - pct).")
    parser.add_argument("--start-date", default=None, help="History start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", default=None, help="History end date, YYYY-MM-DD.")
    parser.add_argument("--adjust-method", choices=["forward", "backward"], default="forward")
    parser.add_argument("--grid-pct", type=float, default=None, help="Grid spacing percentage, e.g. 0.05.")
    parser.add_argument(
        "--bottom-mode",
        choices=[item.value for item in BottomMode],
        default=BottomMode.FIXED.value,
    )
    parser.add_argument("--bottom-price", type=float, default=None, help="Bottom price for fixed mode.")
    parser.add_argument("--bottom-drawdown-pct", type=float, default=None, help="Bottom = first_price * (1 - pct).")
    parser.add_argument("--first-amount", type=float, default=None, help="Planned amount for first grid level.")
    parser.add_argument(
        "--amount-mode",
        choices=[item.value for item in AmountMode],
        default=AmountMode.EQUAL.value,
    )
    parser.add_argument("--amount-step", type=float, default=0.0, help="Arithmetic amount increment per level.")
    parser.add_argument("--lot-size", type=int, default=100)
    parser.add_argument("--fee-rate", type=float, default=0.0)
    parser.add_argument("--min-fee", type=float, default=0.0)
    parser.add_argument("--slippage-rate", type=float, default=0.0)
    parser.add_argument("--price-digits", type=int, default=4)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--basename", default=None)
    parser.add_argument("--preview-rows", type=int, default=20)
    args = parser.parse_args()
    return merge_config_args(args, parser)


def merge_config_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> argparse.Namespace:
    if args.config is None:
        if args.grid_pct is None:
            parser.error("--grid-pct is required unless supplied by --config.")
        if args.first_amount is None:
            parser.error("--first-amount is required unless supplied by --config.")
        return args

    config = load_config_file(args.config)
    defaults = parser.parse_args([])
    merged = vars(args).copy()
    for key, value in config.items():
        arg_key = key.replace("-", "_")
        if arg_key not in merged:
            raise ValueError(f"Unknown config key: {key}")
        current_value = merged[arg_key]
        default_value = getattr(defaults, arg_key)
        if current_value == default_value:
            merged[arg_key] = value
    merged_args = argparse.Namespace(**merged)
    if merged_args.grid_pct is None:
        parser.error("--grid-pct is required unless supplied by --config.")
    if merged_args.first_amount is None:
        parser.error("--first-amount is required unless supplied by --config.")
    if isinstance(merged_args.output_dir, str):
        merged_args.output_dir = Path(merged_args.output_dir)
    return merged_args


def load_history_for_context(args: argparse.Namespace):
    if not args.symbol:
        return None
    try:
        history = load_adjusted_daily_history(args.symbol, adjust_method=args.adjust_method)
        return filter_history(history, start_date=args.start_date, end_date=args.end_date)
    except (FileNotFoundError, ImportError, AttributeError, ValueError) as exc:
        if args.first_price_mode == FirstPriceMode.DRAWDOWN_FROM_HIGH.value:
            raise
        print(f"history_context_warning: {exc}")
        return None


def resolve_first_price(args: argparse.Namespace, history) -> float:
    mode = FirstPriceMode(args.first_price_mode)
    if mode == FirstPriceMode.FIXED:
        if args.first_price is None:
            raise ValueError("--first-price is required when --first-price-mode fixed.")
        return float(args.first_price)

    if mode == FirstPriceMode.DRAWDOWN_FROM_HIGH:
        if not args.symbol:
            raise ValueError("--symbol is required when using drawdown_from_high first price mode.")
        if args.high_drawdown_pct is None:
            raise ValueError("--high-drawdown-pct is required when using drawdown_from_high first price mode.")
        if history is None:
            raise ValueError("adjusted history is required when using drawdown_from_high first price mode.")
        period_high = float(history["high"].max())
        return period_high * (1 - args.high_drawdown_pct)

    raise ValueError(f"Unsupported first price mode: {mode}")


def resolve_bottom_price(args: argparse.Namespace, first_price: float) -> float:
    mode = BottomMode(args.bottom_mode)
    if mode == BottomMode.FIXED:
        if args.bottom_price is None:
            raise ValueError("--bottom-price is required when --bottom-mode fixed.")
        return float(args.bottom_price)
    if mode == BottomMode.DRAWDOWN_FROM_FIRST:
        if args.bottom_drawdown_pct is None:
            raise ValueError("--bottom-drawdown-pct is required when --bottom-mode drawdown_from_first.")
        return first_price * (1 - args.bottom_drawdown_pct)
    raise ValueError(f"Unsupported bottom mode: {mode}")


def print_summary(plan) -> None:
    summary = plan.summary
    print("Grid plan summary")
    print(f"symbol: {summary.symbol or '-'}")
    print(f"first_price: {summary.first_price:.4f}")
    print(f"bottom_price: {summary.bottom_price:.4f}")
    print(f"grid_pct: {summary.grid_pct:.2%}")
    print(f"grid_step: {summary.grid_step:.4f}")
    print(f"grid_count: {summary.grid_count}")
    print(f"max_capital_required: {summary.max_capital_required:.2f}")
    print(f"average_cost: {summary.average_cost:.4f}")
    print(f"floating_pnl_at_bottom: {summary.floating_pnl_at_bottom:.2f}")
    print(f"floating_pnl_pct_at_bottom: {summary.floating_pnl_pct_at_bottom:.2%}")
    print(f"last_buy_price: {summary.last_buy_price:.4f}")
    print(f"covers_bottom: {summary.covers_bottom}")
    print(f"bottom_over_coverage: {summary.bottom_over_coverage:.4f}")
    print(f"total_unused_amount: {summary.total_unused_amount:.2f}")
    print(f"warning_count: {summary.warning_count}")


def print_price_context(context: PriceContext | None) -> None:
    if context is None:
        return
    print("Price context")
    print(f"source: {context.source}")
    print(f"adjusted: {context.adjusted}")
    print(f"adjust_method: {context.adjust_method or '-'}")
    print(f"period_high: {context.period_high if context.period_high is not None else '-'}")
    print(f"period_low: {context.period_low if context.period_low is not None else '-'}")
    print(f"latest_close: {context.latest_close if context.latest_close is not None else '-'}")
    if context.first_price_close_percentile is not None:
        print(f"first_price_close_percentile: {context.first_price_close_percentile:.2%}")
    if context.close_below_first_pct is not None:
        print(f"close_below_first: {context.close_below_first_days} days / {context.close_below_first_pct:.2%}")
    if context.low_touch_first_pct is not None:
        print(f"low_touch_first: {context.low_touch_first_days} days / {context.low_touch_first_pct:.2%}")


def main() -> None:
    args = parse_args()
    history = load_history_for_context(args)
    first_price = resolve_first_price(args, history)
    bottom_price = resolve_bottom_price(args, first_price)
    price_context = None
    if history is not None:
        price_context = build_price_context(
            history=history,
            first_price=first_price,
            source="tdx_offline_adjusted",
            adjusted=True,
            adjust_method=args.adjust_method,
            start_date=args.start_date,
            end_date=args.end_date,
        )
    elif args.first_price_mode == FirstPriceMode.FIXED.value:
        price_context = PriceContext(source="manual", adjusted=False)

    config = GridPlanConfig(
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
    plan = build_grid_plan(config, price_context=price_context)
    basename = args.basename or f"{args.symbol or 'manual'}_grid_plan"
    levels_path, summary_path, report_path = export_plan(plan, args.output_dir, basename)

    print_summary(plan)
    print()
    print_price_context(plan.price_context)
    print()
    print(plan_to_frame(plan).head(args.preview_rows).to_string(index=False))
    print()
    print(f"levels_csv: {levels_path}")
    print(f"summary_csv: {summary_path}")
    if report_path is not None:
        print(f"report_md: {report_path}")


if __name__ == "__main__":
    main()
