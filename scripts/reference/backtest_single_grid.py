from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
ETF_DATA_DIR = PROJECT_ROOT / "etf_data"
DAILY_HISTORY_DIR = ETF_DATA_DIR / "daily"
LEGACY_DAILY_HISTORY_DIR = DATA_DIR / "daily_history"
BACKTEST_DIR = DATA_DIR / "backtests"


@dataclass
class GridConfig:
    symbol: str
    start_date: str | None = None
    end_date: str | None = None
    initial_cash: float = 200_000.0
    base_price: float | None = None
    grid_pct: float = 0.05
    grid_count: int = 10
    order_amount: float = 10_000.0
    increment_ratio: float = 0.05
    retain_profit: bool = True
    retain_multiplier: float = 1.0
    fee_rate: float = 0.0002
    slippage_rate: float = 0.0005
    lot_size: int = 100


@dataclass
class GridLevel:
    level_index: int
    buy_price: float
    sell_price: float
    planned_amount: float


@dataclass
class PositionLot:
    lot_id: int
    level_index: int
    buy_date: pd.Timestamp
    buy_price: float
    buy_price_gross: float
    shares: int
    invested_cash: float
    buy_fee: float
    sell_target: float
    status: str = "open"
    sell_date: pd.Timestamp | None = None
    sell_price: float | None = None
    sell_price_net: float | None = None
    sell_fee: float = 0.0
    sold_shares: int = 0
    retained_shares: int = 0
    realized_pnl: float = 0.0


@dataclass
class BacktestState:
    cash: float
    open_lots: list[PositionLot] = field(default_factory=list)
    retained_shares: int = 0
    retained_cost: float = 0.0
    next_lot_id: int = 1
    trade_records: list[dict[str, Any]] = field(default_factory=list)
    equity_records: list[dict[str, Any]] = field(default_factory=list)
    day_stats: list[dict[str, Any]] = field(default_factory=list)


def compute_grid_count_for_drawdown(grid_pct: float, target_drawdown: float) -> int:
    if not 0 < grid_pct < 1:
        raise ValueError("grid_pct must be between 0 and 1.")
    if not 0 < target_drawdown < 1:
        raise ValueError("target_drawdown must be between 0 and 1.")

    return math.ceil(target_drawdown / grid_pct)


def estimate_full_grid_capital(config: GridConfig) -> float:
    levels = build_grid_levels(config)
    gross_amount = sum(level.planned_amount for level in levels)
    buy_fee = gross_amount * config.fee_rate
    return gross_amount + buy_fee


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Single-symbol ETF grid backtest.")
    parser.add_argument("--symbol", required=True, help="ETF symbol, e.g. sh512800")
    parser.add_argument("--start-date", default=None, help="Backtest start date, YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="Backtest end date, YYYY-MM-DD")
    parser.add_argument("--initial-cash", type=float, default=200000.0, help="Initial cash")
    parser.add_argument("--base-price", type=float, default=None, help="Grid base price. Defaults to first close")
    parser.add_argument("--grid-pct", type=float, default=0.05, help="Grid spacing percentage")
    parser.add_argument("--grid-count", type=int, default=10, help="Number of downward grid levels")
    parser.add_argument("--order-amount", type=float, default=10000.0, help="Base order amount for the first level")
    parser.add_argument(
        "--increment-ratio",
        type=float,
        default=0.05,
        help="Per-level capital increment ratio. Level n uses order_amount * (1 + ratio) ** (n - 1)",
    )
    parser.add_argument(
        "--retain-profit",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether to keep profit shares after sell",
    )
    parser.add_argument(
        "--retain-multiplier",
        type=float,
        default=1.0,
        help="Retained value multiplier relative to gross profit. 1.0 means standard retain-profit mode.",
    )
    parser.add_argument("--fee-rate", type=float, default=0.0002, help="One-way transaction fee rate")
    parser.add_argument("--slippage-rate", type=float, default=0.0005, help="One-way slippage rate")
    parser.add_argument("--lot-size", type=int, default=100, help="Trade lot size")
    return parser.parse_args()


def resolve_history_path(symbol: str) -> Path:
    direct_path = DAILY_HISTORY_DIR / f"{symbol}.csv"
    if direct_path.exists():
        return direct_path

    market_prefix = symbol[:2].lower()
    code = symbol[2:]
    if market_prefix in {"sh", "sz", "bj"}:
        candidate = DAILY_HISTORY_DIR / f"etf_{market_prefix}_{code}_1d.csv"
        if candidate.exists():
            return candidate

    legacy_path = LEGACY_DAILY_HISTORY_DIR / f"{symbol}.csv"
    if legacy_path.exists():
        return legacy_path

    raise FileNotFoundError(
        f"History file not found for symbol={symbol}. "
        f"Searched: {direct_path}, {DAILY_HISTORY_DIR / f'etf_{market_prefix}_{code}_1d.csv'}, {legacy_path}"
    )


def normalize_history_frame(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    rename_map = {}
    if "datetime" in df.columns and "date" not in df.columns:
        rename_map["datetime"] = "date"
    if "vol" in df.columns and "volume" not in df.columns:
        rename_map["vol"] = "volume"
    if rename_map:
        df = df.rename(columns=rename_map)

    required_cols = ["date", "open", "high", "low", "close"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns for {symbol}: {missing_cols}")

    if "symbol" not in df.columns:
        df["symbol"] = symbol
    elif "code" in df.columns:
        market_series = df.get("market")
        if market_series is not None:
            df["symbol"] = (
                market_series.astype(str).str.lower().str.strip() + df["code"].astype(str).str.zfill(6)
            )
        else:
            df["symbol"] = symbol

    df["date"] = pd.to_datetime(df["date"])
    return df


def load_history(symbol: str, start_date: str | None, end_date: str | None) -> pd.DataFrame:
    csv_path = resolve_history_path(symbol)
    df = pd.read_csv(csv_path)
    df = normalize_history_frame(df, symbol=symbol)
    df = df.sort_values("date").reset_index(drop=True)
    if start_date:
        df = df[df["date"] >= pd.Timestamp(start_date)]
    if end_date:
        df = df[df["date"] <= pd.Timestamp(end_date)]
    if df.empty:
        raise ValueError("No history rows after date filtering.")
    return df.reset_index(drop=True)


def load_full_history(symbol: str) -> pd.DataFrame:
    return load_history(symbol=symbol, start_date=None, end_date=None)


def resolve_base_price(
    full_history_df: pd.DataFrame,
    start_date: str | None = None,
    base_price: float | None = None,
    base_price_mode: str = "start_close",
) -> float:
    if base_price is not None:
        return float(base_price)

    if start_date is None:
        start_ts = full_history_df["date"].iloc[0]
    else:
        start_ts = pd.Timestamp(start_date)

    hist = full_history_df[full_history_df["date"] <= start_ts].copy()
    if hist.empty:
        hist = full_history_df.iloc[[0]].copy()

    mode = base_price_mode.lower()
    if mode == "start_close":
        return float(hist["close"].iloc[-1])
    if mode == "ma20":
        return float(hist["close"].tail(20).mean())
    if mode == "high20":
        return float(hist["high"].tail(20).max())
    if mode == "high60":
        return float(hist["high"].tail(60).max())

    raise ValueError(f"Unsupported base_price_mode: {base_price_mode}")


def build_grid_levels(config: GridConfig) -> list[GridLevel]:
    levels: list[GridLevel] = []
    assert config.base_price is not None
    grid_step = config.base_price * config.grid_pct

    for i in range(1, config.grid_count + 1):
        buy_price = config.base_price - grid_step * i
        sell_price = config.base_price - grid_step * (i - 1)
        if buy_price <= 0:
            break
        planned_amount = config.order_amount * ((1 + config.increment_ratio) ** (i - 1))
        levels.append(
            GridLevel(
                level_index=i,
                buy_price=buy_price,
                sell_price=sell_price,
                planned_amount=planned_amount,
            )
        )
    return levels


def levels_to_frame(config: GridConfig, levels: list[GridLevel]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": config.symbol,
                "level_index": level.level_index,
                "buy_price": level.buy_price,
                "sell_price": level.sell_price,
                "planned_amount": level.planned_amount,
            }
            for level in levels
        ]
    )


def lot_round_shares(cash_amount: float, exec_price: float, lot_size: int) -> int:
    raw_shares = math.floor(cash_amount / exec_price)
    return (raw_shares // lot_size) * lot_size


def snapshot_open_level_counts(state: BacktestState) -> dict[int, int]:
    opened_level_counts: dict[int, int] = {}
    for lot in state.open_lots:
        opened_level_counts[lot.level_index] = opened_level_counts.get(lot.level_index, 0) + 1
    return opened_level_counts


def eligible_buy_levels(
    row: pd.Series,
    levels: list[GridLevel],
    opened_level_counts: dict[int, int],
) -> list[GridLevel]:
    return [
        level
        for level in levels
        if opened_level_counts.get(level.level_index, 0) == 0 and row["low"] <= level.buy_price
    ]


def execute_buy_for_level(
    row: pd.Series,
    level: GridLevel,
    config: GridConfig,
    state: BacktestState,
    exec_price_raw: float,
    trigger_type: str,
) -> bool:
    exec_price = exec_price_raw * (1 + config.slippage_rate)
    shares = lot_round_shares(level.planned_amount, exec_price, config.lot_size)
    if shares <= 0:
        return False

    gross_amount = shares * exec_price
    fee = gross_amount * config.fee_rate
    total_cost = gross_amount + fee
    if total_cost > state.cash:
        return False

    state.cash -= total_cost
    lot = PositionLot(
        lot_id=state.next_lot_id,
        level_index=level.level_index,
        buy_date=row["date"],
        buy_price=level.buy_price,
        buy_price_gross=exec_price,
        shares=shares,
        invested_cash=gross_amount,
        buy_fee=fee,
        sell_target=level.sell_price,
    )
    state.next_lot_id += 1
    state.open_lots.append(lot)

    state.trade_records.append(
        {
            "date": row["date"],
            "symbol": config.symbol,
            "action": "buy",
            "lot_id": lot.lot_id,
            "grid_level": lot.level_index,
            "price_plan": level.buy_price,
            "price_exec": exec_price,
            "shares": shares,
            "gross_amount": gross_amount,
            "fee": fee,
            "cash_after": state.cash,
            "sell_target": lot.sell_target,
            "trigger_type": trigger_type,
        }
    )
    return True


def execute_open_gap_buys(
    row: pd.Series,
    levels: list[GridLevel],
    config: GridConfig,
    state: BacktestState,
    opened_level_counts: dict[int, int],
) -> list[int]:
    gap_open_levels = [
        level for level in eligible_buy_levels(row, levels, opened_level_counts) if row["open"] <= level.buy_price
    ]
    opened_levels: list[int] = []

    for level in sorted(gap_open_levels, key=lambda item: item.level_index):
        if execute_buy_for_level(
            row=row,
            level=level,
            config=config,
            state=state,
            exec_price_raw=float(row["open"]),
            trigger_type="gap_open",
        ):
            opened_level_counts[level.level_index] = 1
            opened_levels.append(level.level_index)

    return opened_levels


def execute_intraday_buys(
    row: pd.Series,
    levels: list[GridLevel],
    config: GridConfig,
    state: BacktestState,
    opened_level_counts: dict[int, int],
) -> list[int]:
    intraday_levels = [
        level for level in eligible_buy_levels(row, levels, opened_level_counts) if row["open"] > level.buy_price
    ]
    opened_levels: list[int] = []

    for level in sorted(intraday_levels, key=lambda item: item.level_index):
        if execute_buy_for_level(
            row=row,
            level=level,
            config=config,
            state=state,
            exec_price_raw=level.buy_price,
            trigger_type="intraday_touch",
        ):
            opened_level_counts[level.level_index] = 1
            opened_levels.append(level.level_index)

    return opened_levels


def execute_sell(
    row: pd.Series,
    config: GridConfig,
    state: BacktestState,
    open_only: bool,
) -> list[int]:
    remaining_lots: list[PositionLot] = []
    closed_levels: list[int] = []

    for lot in state.open_lots:
        if open_only:
            if row["open"] < lot.sell_target:
                remaining_lots.append(lot)
                continue
            exec_price_raw = float(row["open"])
            trigger_type = "gap_open"
        else:
            if row["open"] >= lot.sell_target:
                remaining_lots.append(lot)
                continue
            if row["high"] < lot.sell_target:
                remaining_lots.append(lot)
                continue
            exec_price_raw = lot.sell_target
            trigger_type = "intraday_touch"

        exec_price = exec_price_raw * (1 - config.slippage_rate)
        gross_sell = lot.shares * exec_price
        gross_profit = gross_sell - lot.invested_cash
        retain_value = 0.0
        retained_shares = 0

        if config.retain_profit and gross_profit > 0:
            retain_value = gross_profit * config.retain_multiplier
            retained_shares = lot_round_shares(retain_value, exec_price, config.lot_size)
            retained_shares = min(retained_shares, lot.shares)
            if retained_shares >= lot.shares:
                retained_shares = max(0, lot.shares - config.lot_size)

        sold_shares = lot.shares - retained_shares
        if sold_shares <= 0:
            remaining_lots.append(lot)
            continue

        sold_amount = sold_shares * exec_price
        sell_fee = sold_amount * config.fee_rate
        net_sell = sold_amount - sell_fee
        principal_cost = sold_shares * lot.buy_price_gross
        realized_pnl = net_sell - principal_cost

        state.cash += net_sell
        state.retained_shares += retained_shares
        if retained_shares > 0:
            state.retained_cost += retained_shares * lot.buy_price_gross

        lot.status = "closed"
        lot.sell_date = row["date"]
        lot.sell_price = lot.sell_target
        lot.sell_price_net = exec_price
        lot.sell_fee = sell_fee
        lot.sold_shares = sold_shares
        lot.retained_shares = retained_shares
        lot.realized_pnl = realized_pnl

        state.trade_records.append(
            {
                "date": row["date"],
                "symbol": config.symbol,
                "action": "sell",
                "lot_id": lot.lot_id,
                "grid_level": lot.level_index,
                "price_plan": lot.sell_target,
                "price_exec": exec_price,
                "shares": sold_shares,
                "gross_amount": sold_amount,
                "fee": sell_fee,
                "cash_after": state.cash,
                "retained_shares": retained_shares,
                "realized_pnl": realized_pnl,
                "trigger_type": trigger_type,
            }
        )
        closed_levels.append(lot.level_index)

    state.open_lots = remaining_lots
    return closed_levels


def execute_day(
    row: pd.Series,
    levels: list[GridLevel],
    config: GridConfig,
    state: BacktestState,
) -> dict[str, Any]:
    gap_sell_levels = execute_sell(row=row, config=config, state=state, open_only=True)

    opened_level_counts = snapshot_open_level_counts(state)
    gap_buy_levels = execute_open_gap_buys(
        row=row,
        levels=levels,
        config=config,
        state=state,
        opened_level_counts=opened_level_counts,
    )
    intraday_sell_levels = execute_sell(row=row, config=config, state=state, open_only=False)
    intraday_buy_levels = execute_intraday_buys(
        row=row,
        levels=levels,
        config=config,
        state=state,
        opened_level_counts=opened_level_counts,
    )

    day_stat = {
        "date": row["date"],
        "gap_buy_count": len(gap_buy_levels),
        "gap_sell_count": len(gap_sell_levels),
        "intraday_buy_count": len(intraday_buy_levels),
        "intraday_sell_count": len(intraday_sell_levels),
        "total_buy_count": len(gap_buy_levels) + len(intraday_buy_levels),
        "total_sell_count": len(gap_sell_levels) + len(intraday_sell_levels),
        "max_buy_level": max(gap_buy_levels + intraday_buy_levels) if (gap_buy_levels or intraday_buy_levels) else 0,
        "max_sell_level": max(gap_sell_levels + intraday_sell_levels) if (gap_sell_levels or intraday_sell_levels) else 0,
        "opened_levels": ",".join(str(level) for level in gap_buy_levels + intraday_buy_levels),
        "closed_levels": ",".join(str(level) for level in gap_sell_levels + intraday_sell_levels),
    }
    state.day_stats.append(day_stat)
    return day_stat


def record_equity(row: pd.Series, config: GridConfig, state: BacktestState) -> None:
    open_position_value = sum(lot.shares * row["close"] for lot in state.open_lots)
    retained_value = state.retained_shares * row["close"]
    total_equity = state.cash + open_position_value + retained_value
    invested_levels = ",".join(str(lot.level_index) for lot in sorted(state.open_lots, key=lambda x: x.level_index))

    state.equity_records.append(
        {
            "date": row["date"],
            "symbol": config.symbol,
            "close": row["close"],
            "cash": state.cash,
            "open_position_value": open_position_value,
            "retained_value": retained_value,
            "open_lot_count": len(state.open_lots),
            "open_shares": sum(lot.shares for lot in state.open_lots),
            "retained_shares": state.retained_shares,
            "total_equity": total_equity,
            "open_grid_levels": invested_levels,
        }
    )


def summarize_result(
    history_df: pd.DataFrame,
    config: GridConfig,
    levels: list[GridLevel],
    state: BacktestState,
) -> pd.DataFrame:
    equity_df = pd.DataFrame(state.equity_records)
    trade_df = pd.DataFrame(state.trade_records)
    day_stats_df = pd.DataFrame(state.day_stats)

    if equity_df.empty:
        raise ValueError("No equity records generated.")

    equity_df["daily_return"] = equity_df["total_equity"].pct_change().fillna(0.0)
    equity_df["running_peak"] = equity_df["total_equity"].cummax()
    equity_df["drawdown"] = equity_df["total_equity"] / equity_df["running_peak"] - 1.0
    equity_df["capital_in_use"] = equity_df["open_position_value"] + equity_df["retained_value"]

    total_return = equity_df["total_equity"].iloc[-1] / config.initial_cash - 1.0
    total_profit = equity_df["total_equity"].iloc[-1] - config.initial_cash
    max_drawdown = equity_df["drawdown"].min()
    annualized_volatility = equity_df["daily_return"].std(ddof=0) * (252**0.5)
    if not trade_df.empty and "realized_pnl" in trade_df.columns:
        realized_pnl = trade_df.loc[trade_df["action"] == "sell", "realized_pnl"].sum()
    else:
        realized_pnl = 0.0
    holding_days = len(equity_df)
    annualized_return = (1 + total_return) ** (252 / holding_days) - 1 if holding_days > 0 else 0.0
    calmar_ratio = annualized_return / abs(max_drawdown) if max_drawdown < 0 else None
    min_cash = equity_df["cash"].min()
    peak_position_value = (equity_df["open_position_value"] + equity_df["retained_value"]).max()
    max_capital_in_use_idx = equity_df["capital_in_use"].idxmax()
    max_capital_in_use = equity_df.loc[max_capital_in_use_idx, "capital_in_use"]
    max_capital_in_use_date = equity_df.loc[max_capital_in_use_idx, "date"]
    avg_capital_in_use = equity_df["capital_in_use"].mean()
    return_on_max_capital_in_use = total_profit / max_capital_in_use if max_capital_in_use > 0 else None
    return_on_avg_capital_in_use = total_profit / avg_capital_in_use if avg_capital_in_use > 0 else None
    final_close = equity_df["close"].iloc[-1]
    gap_buy_days = int((day_stats_df["gap_buy_count"] > 0).sum()) if not day_stats_df.empty else 0
    gap_sell_days = int((day_stats_df["gap_sell_count"] > 0).sum()) if not day_stats_df.empty else 0
    intraday_buy_days = int((day_stats_df["intraday_buy_count"] > 0).sum()) if not day_stats_df.empty else 0
    intraday_sell_days = int((day_stats_df["intraday_sell_count"] > 0).sum()) if not day_stats_df.empty else 0
    multi_gap_buy_days = int((day_stats_df["gap_buy_count"] >= 2).sum()) if not day_stats_df.empty else 0
    multi_gap_sell_days = int((day_stats_df["gap_sell_count"] >= 2).sum()) if not day_stats_df.empty else 0
    max_gap_buy_count = int(day_stats_df["gap_buy_count"].max()) if not day_stats_df.empty else 0
    max_gap_sell_count = int(day_stats_df["gap_sell_count"].max()) if not day_stats_df.empty else 0

    summary = pd.DataFrame(
        [
            {
                "symbol": config.symbol,
                "start_date": history_df["date"].iloc[0].date().isoformat(),
                "end_date": history_df["date"].iloc[-1].date().isoformat(),
                "base_price": config.base_price,
                "grid_pct": config.grid_pct,
                "grid_count": config.grid_count,
                "order_amount": config.order_amount,
                "increment_ratio": config.increment_ratio,
                "retain_profit": config.retain_profit,
                "retain_multiplier": config.retain_multiplier,
                "fee_rate": config.fee_rate,
                "slippage_rate": config.slippage_rate,
                "initial_cash": config.initial_cash,
                "final_equity": equity_df["total_equity"].iloc[-1],
                "total_return": total_return,
                "annualized_return": annualized_return,
                "annualized_volatility": annualized_volatility,
                "max_drawdown": max_drawdown,
                "calmar_ratio": calmar_ratio,
                "total_profit": total_profit,
                "realized_pnl": realized_pnl,
                "trade_count": len(trade_df),
                "buy_count": int((trade_df["action"] == "buy").sum()) if not trade_df.empty else 0,
                "sell_count": int((trade_df["action"] == "sell").sum()) if not trade_df.empty else 0,
                "min_cash": min_cash,
                "peak_position_value": peak_position_value,
                "max_capital_in_use": max_capital_in_use,
                "max_capital_in_use_date": pd.Timestamp(max_capital_in_use_date).date().isoformat(),
                "avg_capital_in_use": avg_capital_in_use,
                "return_on_max_capital_in_use": return_on_max_capital_in_use,
                "return_on_avg_capital_in_use": return_on_avg_capital_in_use,
                "final_open_lots": len(state.open_lots),
                "final_open_shares": sum(lot.shares for lot in state.open_lots),
                "final_retained_shares": state.retained_shares,
                "final_retained_value": state.retained_shares * final_close,
                "grid_levels": len(levels),
                "gap_buy_days": gap_buy_days,
                "gap_sell_days": gap_sell_days,
                "intraday_buy_days": intraday_buy_days,
                "intraday_sell_days": intraday_sell_days,
                "multi_gap_buy_days": multi_gap_buy_days,
                "multi_gap_sell_days": multi_gap_sell_days,
                "max_gap_buy_count": max_gap_buy_count,
                "max_gap_sell_count": max_gap_sell_count,
            }
        ]
    )
    return summary


def run_backtest(config: GridConfig) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    history_df = load_history(config.symbol, config.start_date, config.end_date)
    if config.base_price is None:
        config.base_price = float(history_df["close"].iloc[0])

    levels = build_grid_levels(config)
    levels_df = levels_to_frame(config, levels)
    state = BacktestState(cash=config.initial_cash)

    for _, row in history_df.iterrows():
        execute_day(row, levels, config, state)
        record_equity(row, config, state)

    trade_df = pd.DataFrame(state.trade_records)
    equity_df = pd.DataFrame(state.equity_records)
    summary_df = summarize_result(history_df, config, levels, state)
    return summary_df, equity_df, trade_df, levels_df


def save_outputs(
    config: GridConfig,
    summary_df: pd.DataFrame,
    equity_df: pd.DataFrame,
    trade_df: pd.DataFrame,
    levels_df: pd.DataFrame,
) -> None:
    run_name = (
        f"{config.symbol}_grid{int(config.grid_pct * 10000):04d}_"
        f"inc{int(config.increment_ratio * 10000):04d}_retain{int(config.retain_profit)}"
    )
    output_dir = BACKTEST_DIR / run_name
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "summary.csv"
    equity_path = output_dir / "equity_curve.csv"
    trade_path = output_dir / "trades.csv"
    levels_path = output_dir / "grid_levels.csv"

    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    equity_df.to_csv(equity_path, index=False, encoding="utf-8-sig")
    trade_df.to_csv(trade_path, index=False, encoding="utf-8-sig")
    levels_df.to_csv(levels_path, index=False, encoding="utf-8-sig")

    print(f"Saved summary to: {summary_path}")
    print(f"Saved equity curve to: {equity_path}")
    print(f"Saved trades to: {trade_path}")
    print(f"Saved grid levels to: {levels_path}")
    print()
    print(summary_df.to_string(index=False))


def main() -> None:
    args = parse_args()
    config = GridConfig(
        symbol=args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        initial_cash=args.initial_cash,
        base_price=args.base_price,
        grid_pct=args.grid_pct,
        grid_count=args.grid_count,
        order_amount=args.order_amount,
        increment_ratio=args.increment_ratio,
        retain_profit=args.retain_profit,
        retain_multiplier=args.retain_multiplier,
        fee_rate=args.fee_rate,
        slippage_rate=args.slippage_rate,
        lot_size=args.lot_size,
    )

    summary_df, equity_df, trade_df, levels_df = run_backtest(config)
    save_outputs(config, summary_df, equity_df, trade_df, levels_df)


if __name__ == "__main__":
    main()
