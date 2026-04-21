from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

try:
    from .backtest_single_grid import BACKTEST_DIR, GridConfig, load_full_history, run_backtest
    from .batch_backtest_single_grid import (
        build_top_candidates,
        compute_feasible_grid_count,
        parse_float_list,
        plot_lines,
    )
except ImportError:
    from backtest_single_grid import BACKTEST_DIR, GridConfig, load_full_history, run_backtest
    from batch_backtest_single_grid import (
        build_top_candidates,
        compute_feasible_grid_count,
        parse_float_list,
        plot_lines,
    )


DEFAULT_SYMBOL = "sz159985"
DEFAULT_BACKTEST_START_DATE = "2020-01-01"
DEFAULT_BACKTEST_END_DATE = "2024-12-31"    
DEFAULT_ANCHOR_CUTOFF_DATE = "2020-01-01"
DEFAULT_ANCHOR_CLOSE_RATIO = 0.80
DEFAULT_ANCHOR_STEP_COUNT = 10
DEFAULT_ANCHOR_STEP_RATIO = 0.005
DEFAULT_GRID_PCTS = "0.05"
DEFAULT_ORDER_AMOUNT = 10_000.0
DEFAULT_MAX_INITIAL_CASH = 200_000.0
DEFAULT_TOP_N = 5
PRICE_DECIMALS = 3

# Anchor construction rule for this scenario:
# 1. Find the highest close before anchor_cutoff_date.
# 2. Compute center_base_price = round(highest_close * anchor_close_ratio, 3).
# 3. Compute anchor_step_size = round((highest_close * anchor_close_ratio) * anchor_step_ratio, 3).
# 4. Generate symmetric base prices from center_base_price +/- anchor_step_count * anchor_step_size.
# 5. Keep center price and all generated prices rounded to 3 decimals.
# Reuse for other symbols with the same logic, for example:
# python scripts/backtest/run_sz159985_pre2020_high80_scan.py --symbol sz159938


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Batch backtest for a single ETF using base prices derived from "
            "80%% of the pre-cutoff highest close, plus/minus symmetric ratio-based price steps."
        )
    )
    parser.add_argument(
        "--symbol",
        default=DEFAULT_SYMBOL,
        help="ETF symbol, default: sz159985. Example: --symbol sz159938",
    )
    parser.add_argument(
        "--backtest-start-date",
        default=DEFAULT_BACKTEST_START_DATE,
        help="Backtest start date, default: 2020-01-01",
    )
    parser.add_argument(
        "--backtest-end-date",
        default=DEFAULT_BACKTEST_END_DATE,
        help="Backtest end date, YYYY-MM-DD. Defaults to the latest available date.",
    )
    parser.add_argument(
        "--anchor-cutoff-date",
        default=DEFAULT_ANCHOR_CUTOFF_DATE,
        help="Use history before this date to compute the pre-cutoff highest close, default: 2020-01-01",
    )
    parser.add_argument(
        "--anchor-close-ratio",
        type=float,
        default=DEFAULT_ANCHOR_CLOSE_RATIO,
        help="Center base price ratio relative to the pre-cutoff highest close, default: 0.80",
    )
    parser.add_argument(
        "--anchor-step-count",
        type=int,
        default=DEFAULT_ANCHOR_STEP_COUNT,
        help="Number of price steps to add above and below the center base price, default: 10",
    )
    parser.add_argument(
        "--anchor-step-ratio",
        type=float,
        default=DEFAULT_ANCHOR_STEP_RATIO,
        help="Neighboring price step ratio relative to center base price, default: 0.005 (0.5%%)",
    )
    parser.add_argument(
        "--grid-pcts",
        default=DEFAULT_GRID_PCTS,
        help="Comma-separated grid pct candidates, default: 0.05",
    )
    parser.add_argument("--order-amount", type=float, default=DEFAULT_ORDER_AMOUNT)
    parser.add_argument("--max-initial-cash", type=float, default=DEFAULT_MAX_INITIAL_CASH)
    parser.add_argument("--increment-ratio", type=float, default=0.05)
    parser.add_argument("--retain-profit", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--retain-multiplier", type=float, default=1.0)
    parser.add_argument("--fee-rate", type=float, default=0.0002)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--lot-size", type=int, default=100)
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    return parser.parse_args()


def resolve_backtest_end_date(full_history_df: pd.DataFrame, end_date: str | None) -> str:
    if end_date:
        return pd.Timestamp(end_date).date().isoformat()
    return pd.Timestamp(full_history_df["date"].max()).date().isoformat()


def build_base_prices(
    full_history_df: pd.DataFrame,
    anchor_cutoff_date: str,
    anchor_close_ratio: float,
    anchor_step_count: int,
    anchor_step_ratio: float,
) -> tuple[float, float, float, list[float]]:
    cutoff_ts = pd.Timestamp(anchor_cutoff_date)
    pre_cutoff_df = full_history_df[full_history_df["date"] < cutoff_ts].copy()
    if pre_cutoff_df.empty:
        raise ValueError(f"No history found before anchor_cutoff_date={anchor_cutoff_date}.")

    highest_close = float(pre_cutoff_df["close"].max())
    raw_center_base_price = highest_close * anchor_close_ratio
    center_base_price = round(raw_center_base_price, PRICE_DECIMALS)
    anchor_step_size = round(raw_center_base_price * anchor_step_ratio, PRICE_DECIMALS)

    prices: list[float] = []
    for offset in range(-anchor_step_count, anchor_step_count + 1):
        price = round(center_base_price + offset * anchor_step_size, PRICE_DECIMALS)
        if price > 0:
            prices.append(price)

    unique_prices = sorted(set(prices))
    if not unique_prices:
        raise ValueError("No positive base prices generated from the provided anchor rule.")

    return highest_close, center_base_price, anchor_step_size, unique_prices


def make_run_id(anchor_label: str, grid_pct: float, order_amount: float, grid_count: int) -> str:
    return (
        f"anchor={anchor_label}"
        f"|grid={grid_pct:.2%}"
        f"|order={int(order_amount)}"
        f"|levels={grid_count}"
    )


def main() -> None:
    args = parse_args()
    grid_pcts = parse_float_list(args.grid_pcts)
    full_history_df = load_full_history(args.symbol)
    resolved_end_date = resolve_backtest_end_date(full_history_df, args.backtest_end_date)

    highest_close, center_base_price, anchor_step_size, base_prices = build_base_prices(
        full_history_df=full_history_df,
        anchor_cutoff_date=args.anchor_cutoff_date,
        anchor_close_ratio=args.anchor_close_ratio,
        anchor_step_count=args.anchor_step_count,
        anchor_step_ratio=args.anchor_step_ratio,
    )

    output_dir = BACKTEST_DIR / (
        f"batch_{args.symbol}_pre2020close80_step{int(anchor_step_size * 1000):03d}_"
        f"cash{int(args.max_initial_cash)}_order{int(args.order_amount)}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_frames: list[pd.DataFrame] = []
    equity_frames: list[pd.DataFrame] = []

    for base_price in base_prices:
        anchor_label = f"fixed:{base_price:.3f}"
        for grid_pct in grid_pcts:
            grid_count, required_capital = compute_feasible_grid_count(
                symbol=args.symbol,
                start_date=args.backtest_start_date,
                end_date=resolved_end_date,
                base_price=base_price,
                grid_pct=grid_pct,
                order_amount=args.order_amount,
                increment_ratio=args.increment_ratio,
                retain_profit=args.retain_profit,
                retain_multiplier=args.retain_multiplier,
                fee_rate=args.fee_rate,
                slippage_rate=args.slippage_rate,
                lot_size=args.lot_size,
                max_initial_cash=args.max_initial_cash,
            )

            config = GridConfig(
                symbol=args.symbol,
                start_date=args.backtest_start_date,
                end_date=resolved_end_date,
                initial_cash=args.max_initial_cash,
                base_price=base_price,
                grid_pct=grid_pct,
                grid_count=grid_count,
                order_amount=args.order_amount,
                increment_ratio=args.increment_ratio,
                retain_profit=args.retain_profit,
                retain_multiplier=args.retain_multiplier,
                fee_rate=args.fee_rate,
                slippage_rate=args.slippage_rate,
                lot_size=args.lot_size,
            )
            run_id = make_run_id(anchor_label, grid_pct, args.order_amount, grid_count)
            summary_df, equity_df, _, _ = run_backtest(config)

            summary_df = summary_df.assign(
                run_id=run_id,
                anchor_search_mode="fixed_range",
                anchor_label=anchor_label,
                base_mode="fixed_price",
                required_capital=required_capital,
                max_initial_cash=args.max_initial_cash,
                capital_utilization=required_capital / args.max_initial_cash if args.max_initial_cash else None,
                implied_covered_drawdown=min(grid_pct * grid_count, 1.0),
                anchor_cutoff_date=args.anchor_cutoff_date,
                anchor_close_ratio=args.anchor_close_ratio,
                pre_cutoff_highest_close=highest_close,
                center_base_price=center_base_price,
                anchor_step_ratio=args.anchor_step_ratio,
                anchor_step_size=anchor_step_size,
                anchor_step_count=args.anchor_step_count,
            )

            equity_df = equity_df.assign(
                run_id=run_id,
                nav=equity_df["total_equity"] / args.max_initial_cash,
            )
            equity_df["running_peak"] = equity_df["total_equity"].cummax()
            equity_df["drawdown"] = equity_df["total_equity"] / equity_df["running_peak"] - 1.0

            summary_frames.append(summary_df)
            equity_frames.append(equity_df)

    summary_all = pd.concat(summary_frames, ignore_index=True)
    equity_all = pd.concat(equity_frames, ignore_index=True)

    summary_all = summary_all.sort_values(
        ["total_return", "calmar_ratio", "annualized_return"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    top_candidates_df = build_top_candidates(summary_all, top_n=args.top_n)

    summary_path = output_dir / "summary_all.csv"
    top_candidates_path = output_dir / "top_candidates.csv"
    equity_path = output_dir / "equity_all.csv"
    best_summary_path = output_dir / "best_summary.csv"
    best_equity_path = output_dir / "best_equity.csv"
    nav_png = output_dir / "nav_compare.png"
    dd_png = output_dir / "drawdown_compare.png"

    summary_all.to_csv(summary_path, index=False, encoding="utf-8-sig")
    top_candidates_df.to_csv(top_candidates_path, index=False, encoding="utf-8-sig")
    equity_all.to_csv(equity_path, index=False, encoding="utf-8-sig")
    summary_all.head(1).to_csv(best_summary_path, index=False, encoding="utf-8-sig")

    best_run_id = str(summary_all.iloc[0]["run_id"])
    equity_all[equity_all["run_id"] == best_run_id].to_csv(best_equity_path, index=False, encoding="utf-8-sig")

    plot_lines(
        curve_df=equity_all,
        value_col="nav",
        title=f"{args.symbol} NAV Comparison ({args.backtest_start_date} to {resolved_end_date})",
        ylabel="NAV",
        output_path=nav_png,
    )
    plot_lines(
        curve_df=equity_all,
        value_col="drawdown",
        title=f"{args.symbol} Drawdown Comparison ({args.backtest_start_date} to {resolved_end_date})",
        ylabel="Drawdown",
        output_path=dd_png,
    )

    print(f"Pre-cutoff highest close: {highest_close:.3f}")
    print(f"Center base price ({args.anchor_close_ratio:.0%} of pre-cutoff close): {center_base_price:.3f}")
    print(f"Anchor step size ({args.anchor_step_ratio:.2%} of center base price): {anchor_step_size:.3f}")
    print("Generated base prices:", ",".join(f"{price:.3f}" for price in base_prices))
    print(f"Saved summary to: {summary_path}")
    print(f"Saved top candidates to: {top_candidates_path}")
    print(f"Saved equity panel to: {equity_path}")
    print(f"Saved best summary to: {best_summary_path}")
    print(f"Saved best equity curve to: {best_equity_path}")
    print(f"Saved NAV comparison chart to: {nav_png}")
    print(f"Saved drawdown comparison chart to: {dd_png}")


if __name__ == "__main__":
    main()
