from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .grid_plan import FLOAT_FORMAT, calc_fee, frame_to_markdown
from .models import GridLevel, GridPlan


PRECISION = 3


@dataclass
class OpenLot:
    level_index: int
    buy_date: pd.Timestamp
    buy_price: float
    buy_exec_price: float
    shares: int
    invested_amount: float
    buy_fee: float
    total_cost: float
    sell_target: float


@dataclass
class BacktestState:
    cash: float
    open_lots: list[OpenLot] = field(default_factory=list)
    trade_records: list[dict[str, Any]] = field(default_factory=list)
    equity_records: list[dict[str, Any]] = field(default_factory=list)
    day_records: list[dict[str, Any]] = field(default_factory=list)


def q3(value: float | int) -> float:
    return round(float(value), PRECISION)


def q3_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    float_cols = result.select_dtypes(include=["float"]).columns
    for col in float_cols:
        result[col] = result[col].round(PRECISION)
    return result


def normalize_history_for_backtest(history: pd.DataFrame) -> pd.DataFrame:
    df = history.sort_values("date").copy()
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce").round(PRECISION)
    df = df.dropna(subset=["open", "high", "low", "close"])
    if df.empty:
        raise ValueError("No valid OHLC rows for backtest.")
    return df.reset_index(drop=True)


def run_grid_v1_backtest(
    plan: GridPlan,
    history: pd.DataFrame,
    initial_cash: float | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run a conservative daily replay for grid 1.0.

    Conservative means a lot bought today cannot be sold later in the same day,
    because daily bars do not reveal the intraday low/high order.
    """

    df = normalize_history_for_backtest(history)
    cash = q3(initial_cash if initial_cash is not None else plan.summary.max_capital_required)
    state = BacktestState(cash=cash)
    levels = sorted(plan.levels, key=lambda item: item.level_index)

    for _, row in df.iterrows():
        date = row["date"]
        open_price = q3(row["open"])
        high_price = q3(row["high"])
        low_price = q3(row["low"])
        close_price = q3(row["close"])

        sold_levels = execute_sells(
            date=date,
            open_price=open_price,
            high_price=high_price,
            plan=plan,
            state=state,
        )
        bought_levels = execute_buys(
            date=date,
            open_price=open_price,
            low_price=low_price,
            levels=levels,
            plan=plan,
            state=state,
        )
        record_day(date, close_price, bought_levels, sold_levels, state)
        record_equity(date, close_price, plan, state)

    trades = q3_frame(pd.DataFrame(state.trade_records))
    equity = q3_frame(pd.DataFrame(state.equity_records))
    days = pd.DataFrame(state.day_records)
    summary = q3_frame(summarize_backtest(plan, df, state, cash, trades, equity))
    return trades, equity, days, summary


def execute_sells(
    date: pd.Timestamp,
    open_price: float,
    high_price: float,
    plan: GridPlan,
    state: BacktestState,
) -> list[int]:
    sold_levels: list[int] = []
    remaining: list[OpenLot] = []
    for lot in state.open_lots:
        if open_price >= lot.sell_target:
            exec_raw = open_price
            trigger_type = "gap_open"
        elif high_price >= lot.sell_target:
            exec_raw = lot.sell_target
            trigger_type = "intraday_touch"
        else:
            remaining.append(lot)
            continue

        exec_price = q3(exec_raw * (1 - plan.config.slippage_rate))
        gross_amount = q3(lot.shares * exec_price)
        sell_fee = q3(calc_fee(gross_amount, plan.config.fee_rate, plan.config.min_fee))
        net_amount = q3(gross_amount - sell_fee)
        realized_pnl = q3(net_amount - lot.total_cost)
        state.cash = q3(state.cash + net_amount)
        state.trade_records.append(
            {
                "date": date,
                "symbol": plan.config.symbol,
                "action": "sell",
                "level_index": lot.level_index,
                "plan_price": lot.sell_target,
                "exec_price": exec_price,
                "shares": lot.shares,
                "gross_amount": gross_amount,
                "fee": sell_fee,
                "net_amount": net_amount,
                "realized_pnl": realized_pnl,
                "cash_after": state.cash,
                "trigger_type": trigger_type,
            }
        )
        sold_levels.append(lot.level_index)
    state.open_lots = remaining
    return sold_levels


def execute_buys(
    date: pd.Timestamp,
    open_price: float,
    low_price: float,
    levels: list[GridLevel],
    plan: GridPlan,
    state: BacktestState,
) -> list[int]:
    open_level_indexes = {lot.level_index for lot in state.open_lots}
    bought_levels: list[int] = []
    for level in levels:
        if level.level_index in open_level_indexes:
            continue
        if low_price > level.buy_price:
            continue

        exec_raw = open_price if open_price <= level.buy_price else level.buy_price
        trigger_type = "gap_open" if open_price <= level.buy_price else "intraday_touch"
        exec_price = q3(exec_raw * (1 + plan.config.slippage_rate))
        invested_amount = q3(level.shares * exec_price)
        buy_fee = q3(calc_fee(invested_amount, plan.config.fee_rate, plan.config.min_fee))
        total_cost = q3(invested_amount + buy_fee)
        if level.shares <= 0 or total_cost > state.cash:
            continue

        state.cash = q3(state.cash - total_cost)
        lot = OpenLot(
            level_index=level.level_index,
            buy_date=date,
            buy_price=level.buy_price,
            buy_exec_price=exec_price,
            shares=level.shares,
            invested_amount=invested_amount,
            buy_fee=buy_fee,
            total_cost=total_cost,
            sell_target=level.sell_price,
        )
        state.open_lots.append(lot)
        open_level_indexes.add(level.level_index)
        bought_levels.append(level.level_index)
        state.trade_records.append(
            {
                "date": date,
                "symbol": plan.config.symbol,
                "action": "buy",
                "level_index": level.level_index,
                "plan_price": level.buy_price,
                "exec_price": exec_price,
                "shares": level.shares,
                "gross_amount": invested_amount,
                "fee": buy_fee,
                "net_amount": total_cost,
                "realized_pnl": 0.0,
                "cash_after": state.cash,
                "trigger_type": trigger_type,
            }
        )
    return bought_levels


def record_day(
    date: pd.Timestamp,
    close_price: float,
    bought_levels: list[int],
    sold_levels: list[int],
    state: BacktestState,
) -> None:
    state.day_records.append(
        {
            "date": date,
            "close": close_price,
            "buy_count": len(bought_levels),
            "sell_count": len(sold_levels),
            "bought_levels": ",".join(str(item) for item in bought_levels),
            "sold_levels": ",".join(str(item) for item in sold_levels),
        }
    )


def record_equity(date: pd.Timestamp, close_price: float, plan: GridPlan, state: BacktestState) -> None:
    open_position_value = q3(sum(lot.shares * close_price for lot in state.open_lots))
    open_cost = q3(sum(lot.total_cost for lot in state.open_lots))
    total_equity = q3(state.cash + open_position_value)
    floating_pnl = q3(open_position_value - open_cost)
    state.equity_records.append(
        {
            "date": date,
            "symbol": plan.config.symbol,
            "close": close_price,
            "cash": state.cash,
            "open_position_value": open_position_value,
            "open_cost": open_cost,
            "floating_pnl": floating_pnl,
            "open_lot_count": len(state.open_lots),
            "open_shares": sum(lot.shares for lot in state.open_lots),
            "total_equity": total_equity,
            "open_grid_levels": ",".join(str(lot.level_index) for lot in sorted(state.open_lots, key=lambda item: item.level_index)),
        }
    )


def summarize_backtest(
    plan: GridPlan,
    history: pd.DataFrame,
    state: BacktestState,
    initial_cash: float,
    trades: pd.DataFrame,
    equity: pd.DataFrame,
) -> pd.DataFrame:
    if equity.empty:
        raise ValueError("No equity rows generated.")

    equity_work = equity.copy()
    equity_work["running_peak"] = equity_work["total_equity"].cummax()
    equity_work["drawdown"] = equity_work["total_equity"] / equity_work["running_peak"] - 1
    equity_work["capital_in_use"] = equity_work["open_position_value"]

    sells = trades[trades["action"] == "sell"] if not trades.empty else pd.DataFrame()
    buys = trades[trades["action"] == "buy"] if not trades.empty else pd.DataFrame()
    final_equity = float(equity_work["total_equity"].iloc[-1])
    total_return = final_equity / initial_cash - 1 if initial_cash else 0.0
    max_capital_in_use = float(equity_work["capital_in_use"].max())
    max_floating_loss = float(equity_work["floating_pnl"].min())
    max_drawdown = float(equity_work["drawdown"].min())
    realized_pnl = float(sells["realized_pnl"].sum()) if not sells.empty else 0.0
    untouched_levels = sorted(
        set(level.level_index for level in plan.levels)
        - set(int(item) for item in buys["level_index"].unique()) if not buys.empty else set(level.level_index for level in plan.levels)
    )

    return pd.DataFrame(
        [
            {
                "symbol": plan.config.symbol,
                "start_date": history["date"].iloc[0].date().isoformat(),
                "end_date": history["date"].iloc[-1].date().isoformat(),
                "adjust_method": "forward",
                "bar_mode": "daily_conservative",
                "initial_cash": initial_cash,
                "final_equity": final_equity,
                "total_return": total_return,
                "realized_pnl": realized_pnl,
                "buy_count": int(len(buys)),
                "sell_count": int(len(sells)),
                "open_lot_count": int(equity_work["open_lot_count"].iloc[-1]),
                "max_capital_in_use": max_capital_in_use,
                "max_floating_loss": max_floating_loss,
                "max_drawdown": max_drawdown,
                "peak_capital_usage_pct": max_capital_in_use / initial_cash if initial_cash else 0.0,
                "final_cash": float(equity_work["cash"].iloc[-1]),
                "final_position_value": float(equity_work["open_position_value"].iloc[-1]),
                "untouched_levels": ",".join(str(item) for item in untouched_levels),
            }
        ]
    )


def render_backtest_report(summary: pd.DataFrame, trades: pd.DataFrame, equity: pd.DataFrame) -> str:
    row = summary.iloc[0].to_dict()
    lines = [
        "# 网格 1.0 历史回放报告",
        "",
        "## 回测摘要",
        "",
        f"- 标的代码 (symbol): {row.get('symbol', '-')}",
        f"- 回测起始日期 (start_date): {row.get('start_date', '-')}",
        f"- 回测结束日期 (end_date): {row.get('end_date', '-')}",
        f"- 复权方式 (adjust_method): {row.get('adjust_method', '-')}",
        f"- K线模式 (bar_mode): {row.get('bar_mode', '-')}",
        f"- 初始资金 (initial_cash): {row.get('initial_cash', 0):.3f}",
        f"- 期末权益 (final_equity): {row.get('final_equity', 0):.3f}",
        f"- 总收益率 (total_return): {row.get('total_return', 0):.3%}",
        f"- 已实现利润 (realized_pnl): {row.get('realized_pnl', 0):.3f}",
        f"- 买入次数 (buy_count): {row.get('buy_count', 0)}",
        f"- 卖出次数 (sell_count): {row.get('sell_count', 0)}",
        f"- 期末未平仓网格数 (open_lot_count): {row.get('open_lot_count', 0)}",
        f"- 最大资金占用 (max_capital_in_use): {row.get('max_capital_in_use', 0):.3f}",
        f"- 最大浮亏 (max_floating_loss): {row.get('max_floating_loss', 0):.3f}",
        f"- 最大回撤 (max_drawdown): {row.get('max_drawdown', 0):.3%}",
        f"- 资金使用率峰值 (peak_capital_usage_pct): {row.get('peak_capital_usage_pct', 0):.3%}",
        f"- 从未触发网格 (untouched_levels): {row.get('untouched_levels') or '-'}",
        "",
        "说明：本回测使用前复权日线数据，并采用保守日线回放。同一天买入的网格不会在当天卖出，因为日线无法确认盘中高低点先后顺序。",
        "",
    ]
    if not trades.empty:
        lines.extend(["## 最近交易记录", "", frame_to_markdown(trades.tail(20)), ""])
    if not equity.empty:
        preview_cols = [
            "date",
            "close",
            "cash",
            "open_position_value",
            "floating_pnl",
            "open_lot_count",
            "total_equity",
            "open_grid_levels",
        ]
        lines.extend(["## 最近权益记录", "", frame_to_markdown(equity[preview_cols].tail(20)), ""])
    return "\n".join(lines)


def export_backtest(
    trades: pd.DataFrame,
    equity: pd.DataFrame,
    days: pd.DataFrame,
    summary: pd.DataFrame,
    output_dir: Path,
    basename: str,
) -> tuple[Path, Path, Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    trades_path = output_dir / f"{basename}_backtest_trades.csv"
    equity_path = output_dir / f"{basename}_backtest_equity.csv"
    days_path = output_dir / f"{basename}_backtest_days.csv"
    summary_path = output_dir / f"{basename}_backtest_summary.csv"
    report_path = output_dir / f"{basename}_backtest_report.md"
    trades.to_csv(trades_path, index=False, encoding="utf-8-sig", float_format=FLOAT_FORMAT)
    equity.to_csv(equity_path, index=False, encoding="utf-8-sig", float_format=FLOAT_FORMAT)
    days.to_csv(days_path, index=False, encoding="utf-8-sig", float_format=FLOAT_FORMAT)
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig", float_format=FLOAT_FORMAT)
    report_path.write_text(render_backtest_report(summary, trades, equity), encoding="utf-8")
    return trades_path, equity_path, days_path, summary_path, report_path
