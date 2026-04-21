from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

try:
    from .backtest_single_grid import (
        BACKTEST_DIR,
        GridConfig,
        estimate_full_grid_capital,
        load_full_history,
        resolve_base_price,
        run_backtest,
    )
except ImportError:
    from backtest_single_grid import (
        BACKTEST_DIR,
        GridConfig,
        estimate_full_grid_capital,
        load_full_history,
        resolve_base_price,
        run_backtest,
    )


DEFAULT_BASE_MODES = ["start_close", "ma20", "high60"]
DEFAULT_GRID_PCTS = [0.05, 0.07, 0.10]
DEFAULT_ORDER_AMOUNT = 10000.0
DEFAULT_MAX_INITIAL_CASH = 200000.0
DEFAULT_LOOKBACK_YEARS = 3
DEFAULT_TOP_N = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch backtest for a single ETF grid strategy.")
    parser.add_argument("--symbol", required=True, help="ETF symbol, e.g. sh512800")
    parser.add_argument("--start-date", default=None, help="Backtest start date, YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="Backtest end date, YYYY-MM-DD")
    parser.add_argument(
        "--lookback-years",
        type=int,
        default=DEFAULT_LOOKBACK_YEARS,
        help="If start-date is omitted, use the most recent N years ending at end-date/latest date.",
    )
    parser.add_argument(
        "--base-modes",
        default=",".join(DEFAULT_BASE_MODES),
        help="Comma-separated base price modes: start_close, ma20, high20, high60",
    )
    parser.add_argument(
        "--base-prices",
        default=None,
        help="Optional comma-separated fixed base prices, e.g. 0.82,0.86,0.91",
    )
    parser.add_argument(
        "--grid-pcts",
        default=",".join(f"{value:.2f}" for value in DEFAULT_GRID_PCTS),
        help="Comma-separated grid size candidates, e.g. 0.05,0.07,0.10",
    )
    parser.add_argument(
        "--order-amount",
        type=float,
        default=DEFAULT_ORDER_AMOUNT,
        help="First grid buy amount. Fixed to 10000 by default.",
    )
    parser.add_argument(
        "--max-initial-cash",
        type=float,
        default=DEFAULT_MAX_INITIAL_CASH,
        help="Maximum total capital allowed for a parameter set.",
    )
    parser.add_argument("--increment-ratio", type=float, default=0.05, help="Per-level increment ratio")
    parser.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_TOP_N,
        help="Number of top candidates to keep for each ranking metric in top_candidates.csv",
    )
    parser.add_argument("--retain-profit", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--retain-multiplier", type=float, default=1.0)
    parser.add_argument("--fee-rate", type=float, default=0.0002)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--lot-size", type=int, default=100)
    return parser.parse_args()


def parse_float_list(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def parse_str_list(raw: str) -> list[str]:
    normalized = raw.strip().lower()
    if normalized in {"", "none", "null", "off"}:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def build_anchor_candidates(
    full_history_df: pd.DataFrame,
    start_date: str,
    base_modes: list[str],
    base_prices: list[float],
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    seen_keys: set[tuple[str, str]] = set()

    for base_mode in base_modes:
        base_price = resolve_base_price(
            full_history_df=full_history_df,
            start_date=start_date,
            base_price=None,
            base_price_mode=base_mode,
        )
        key = ("rule", base_mode)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        candidates.append(
            {
                "anchor_search_mode": "rule",
                "anchor_label": base_mode,
                "base_mode": base_mode,
                "base_price": float(base_price),
            }
        )

    for base_price in base_prices:
        rounded_price = round(float(base_price), 6)
        key = ("fixed_range", f"{rounded_price:.6f}")
        if key in seen_keys:
            continue
        seen_keys.add(key)
        candidates.append(
            {
                "anchor_search_mode": "fixed_range",
                "anchor_label": f"fixed:{rounded_price:.4f}",
                "base_mode": "fixed_price",
                "base_price": rounded_price,
            }
        )

    if not candidates:
        raise ValueError("At least one anchor candidate is required. Set --base-modes and/or --base-prices.")

    return candidates


def resolve_backtest_window(
    full_history_df: pd.DataFrame,
    start_date: str | None,
    end_date: str | None,
    lookback_years: int,
) -> tuple[str, str]:
    resolved_end = pd.Timestamp(end_date) if end_date else pd.Timestamp(full_history_df["date"].max())
    if start_date:
        resolved_start = pd.Timestamp(start_date)
    else:
        resolved_start = resolved_end - pd.DateOffset(years=lookback_years)

    return resolved_start.date().isoformat(), resolved_end.date().isoformat()


def compute_feasible_grid_count(
    symbol: str,
    start_date: str,
    end_date: str,
    base_price: float,
    grid_pct: float,
    order_amount: float,
    increment_ratio: float,
    retain_profit: bool,
    retain_multiplier: float,
    fee_rate: float,
    slippage_rate: float,
    lot_size: int,
    max_initial_cash: float,
) -> tuple[int, float]:
    max_grid_count = 0
    required_capital = 0.0

    for grid_count in range(1, 100):
        probe_config = GridConfig(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_cash=0.0,
            base_price=base_price,
            grid_pct=grid_pct,
            grid_count=grid_count,
            order_amount=order_amount,
            increment_ratio=increment_ratio,
            retain_profit=retain_profit,
            retain_multiplier=retain_multiplier,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            lot_size=lot_size,
        )
        required_capital = estimate_full_grid_capital(probe_config)
        if required_capital > max_initial_cash:
            break
        max_grid_count = grid_count

    if max_grid_count <= 0:
        raise ValueError("No feasible grid count under the max_initial_cash constraint.")

    final_probe = GridConfig(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        initial_cash=0.0,
        base_price=base_price,
        grid_pct=grid_pct,
        grid_count=max_grid_count,
        order_amount=order_amount,
        increment_ratio=increment_ratio,
        retain_profit=retain_profit,
        retain_multiplier=retain_multiplier,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        lot_size=lot_size,
    )
    return max_grid_count, estimate_full_grid_capital(final_probe)


def make_run_id(anchor_label: str, grid_pct: float, order_amount: float, grid_count: int) -> str:
    return (
        f"anchor={anchor_label}"
        f"|grid={grid_pct:.2%}"
        f"|order={int(order_amount)}"
        f"|levels={grid_count}"
    )


def plot_lines(
    curve_df: pd.DataFrame,
    value_col: str,
    title: str,
    ylabel: str,
    output_path: Path,
) -> None:
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    sns.set_theme(style="whitegrid", font="SimHei")

    run_count = curve_df["run_id"].nunique()
    fig_width = max(14, 12 + run_count * 0.25)
    plt.figure(figsize=(fig_width, 8))

    for run_id, sub_df in curve_df.groupby("run_id"):
        plt.plot(sub_df["date"], sub_df[value_col], linewidth=1.4, label=run_id)

    plt.title(title, fontsize=14)
    plt.xlabel("Date")
    plt.ylabel(ylabel)
    plt.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=8, frameon=False)
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


def build_top_candidates(summary_all: pd.DataFrame, top_n: int) -> pd.DataFrame:
    ranking_specs = [
        {"metric": "total_return", "ascending": False, "ranking_value_col": "total_return"},
        {"metric": "calmar_ratio", "ascending": False, "ranking_value_col": "calmar_ratio"},
        {
            "metric": "return_on_avg_capital_in_use",
            "ascending": False,
            "ranking_value_col": "return_on_avg_capital_in_use",
        },
        {
            "metric": "return_on_max_capital_in_use",
            "ascending": False,
            "ranking_value_col": "return_on_max_capital_in_use",
        },
        {"metric": "max_drawdown", "ascending": True, "ranking_value_col": "max_drawdown_abs"},
    ]
    candidate_frames: list[pd.DataFrame] = []

    for spec in ranking_specs:
        metric = str(spec["metric"])
        ascending = bool(spec["ascending"])
        ranking_value_col = str(spec["ranking_value_col"])
        if metric not in summary_all.columns:
            continue
        ranked = summary_all[summary_all[metric].notna()].copy()
        if ranked.empty:
            continue
        if metric == "max_drawdown":
            ranked["max_drawdown_abs"] = ranked["max_drawdown"].abs()
        ranked = ranked.sort_values(
            [ranking_value_col, "total_return", "calmar_ratio"],
            ascending=[ascending, False, False],
        ).head(top_n).copy()
        ranked.insert(0, "ranking_metric", metric)
        ranked.insert(1, "ranking_direction", "asc" if ascending else "desc")
        ranked.insert(2, "ranking_value", ranked[ranking_value_col])
        ranked.insert(3, "ranking_order", range(1, len(ranked) + 1))
        if "max_drawdown_abs" in ranked.columns:
            ranked = ranked.drop(columns=["max_drawdown_abs"])
        candidate_frames.append(ranked)

    if not candidate_frames:
        return pd.DataFrame()

    return pd.concat(candidate_frames, ignore_index=True)


def main() -> None:
    args = parse_args()
    base_modes = parse_str_list(args.base_modes)
    base_prices = parse_float_list(args.base_prices) if args.base_prices else []
    grid_pcts = parse_float_list(args.grid_pcts)
    full_history_df = load_full_history(args.symbol)
    resolved_start_date, resolved_end_date = resolve_backtest_window(
        full_history_df=full_history_df,
        start_date=args.start_date,
        end_date=args.end_date,
        lookback_years=args.lookback_years,
    )
    anchor_candidates = build_anchor_candidates(
        full_history_df=full_history_df,
        start_date=resolved_start_date,
        base_modes=base_modes,
        base_prices=base_prices,
    )

    output_dir = BACKTEST_DIR / (
        f"batch_{args.symbol}_3y_cash{int(args.max_initial_cash)}_order{int(args.order_amount)}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_frames: list[pd.DataFrame] = []
    equity_frames: list[pd.DataFrame] = []

    for anchor in anchor_candidates:
        base_mode = str(anchor["base_mode"])
        base_price = float(anchor["base_price"])
        anchor_label = str(anchor["anchor_label"])
        anchor_search_mode = str(anchor["anchor_search_mode"])
        for grid_pct in grid_pcts:
            grid_count, required_capital = compute_feasible_grid_count(
                symbol=args.symbol,
                start_date=resolved_start_date,
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

            initial_cash = args.max_initial_cash
            config = GridConfig(
                symbol=args.symbol,
                start_date=resolved_start_date,
                end_date=resolved_end_date,
                initial_cash=initial_cash,
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
            implied_covered_drawdown = min(grid_pct * grid_count, 1.0)

            summary_df = summary_df.assign(
                run_id=run_id,
                anchor_search_mode=anchor_search_mode,
                anchor_label=anchor_label,
                base_mode=base_mode,
                required_capital=required_capital,
                max_initial_cash=args.max_initial_cash,
                capital_utilization=required_capital / args.max_initial_cash if args.max_initial_cash else None,
                implied_covered_drawdown=implied_covered_drawdown,
                lookback_years=args.lookback_years,
            )

            equity_df = equity_df.assign(
                run_id=run_id,
                nav=equity_df["total_equity"] / initial_cash,
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

    summary_path = output_dir / "summary_all.csv"
    equity_path = output_dir / "equity_all.csv"
    top_candidates_path = output_dir / "top_candidates.csv"
    nav_png = output_dir / "nav_compare.png"
    dd_png = output_dir / "drawdown_compare.png"
    best_summary_path = output_dir / "best_summary.csv"
    best_equity_path = output_dir / "best_equity.csv"
    top_candidates_df = build_top_candidates(summary_all, top_n=args.top_n)

    summary_all.to_csv(summary_path, index=False, encoding="utf-8-sig")
    equity_all.to_csv(equity_path, index=False, encoding="utf-8-sig")
    top_candidates_df.to_csv(top_candidates_path, index=False, encoding="utf-8-sig")
    summary_all.head(1).to_csv(best_summary_path, index=False, encoding="utf-8-sig")

    best_run_id = summary_all.iloc[0]["run_id"]
    equity_all[equity_all["run_id"] == best_run_id].to_csv(best_equity_path, index=False, encoding="utf-8-sig")

    plot_lines(
        curve_df=equity_all,
        value_col="nav",
        title=f"{args.symbol} Grid Strategy NAV Comparison ({resolved_start_date} to {resolved_end_date})",
        ylabel="NAV",
        output_path=nav_png,
    )
    plot_lines(
        curve_df=equity_all,
        value_col="drawdown",
        title=f"{args.symbol} Grid Strategy Drawdown Comparison ({resolved_start_date} to {resolved_end_date})",
        ylabel="Drawdown",
        output_path=dd_png,
    )

    print(f"Saved summary to: {summary_path}")
    print(f"Saved equity panel to: {equity_path}")
    print(f"Saved top candidates to: {top_candidates_path}")
    print(f"Saved best summary to: {best_summary_path}")
    print(f"Saved best equity curve to: {best_equity_path}")
    print(f"Saved NAV comparison chart to: {nav_png}")
    print(f"Saved drawdown comparison chart to: {dd_png}")
    print()
    print(
        summary_all[
            [
                "run_id",
                "base_price",
                "grid_pct",
                "grid_count",
                "order_amount",
                "initial_cash",
                "required_capital",
                "capital_utilization",
                "implied_covered_drawdown",
                "final_equity",
                "total_return",
                "annualized_return",
                "max_drawdown",
                "calmar_ratio",
                "total_profit",
                "max_capital_in_use",
                "max_capital_in_use_date",
                "avg_capital_in_use",
                "return_on_max_capital_in_use",
                "return_on_avg_capital_in_use",
                "trade_count",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
