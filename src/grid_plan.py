from __future__ import annotations

import math
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .models import AmountMode, GridLevel, GridPlan, GridPlanConfig, PriceContext, StressSummary

FLOAT_FORMAT = "%.3f"


def validate_config(config: GridPlanConfig) -> None:
    if config.first_price <= 0:
        raise ValueError("first_price must be positive.")
    if not 0 < config.grid_pct < 1:
        raise ValueError("grid_pct must be between 0 and 1.")
    if config.bottom_price <= 0:
        raise ValueError("bottom_price must be positive.")
    if config.bottom_price >= config.first_price:
        raise ValueError("bottom_price must be lower than first_price.")
    if config.first_amount <= 0:
        raise ValueError("first_amount must be positive.")
    if config.lot_size <= 0:
        raise ValueError("lot_size must be positive.")
    if config.fee_rate < 0:
        raise ValueError("fee_rate must not be negative.")
    if config.min_fee < 0:
        raise ValueError("min_fee must not be negative.")
    if config.slippage_rate < 0:
        raise ValueError("slippage_rate must not be negative.")
    if config.amount_mode == AmountMode.ARITHMETIC and config.amount_step < 0:
        raise ValueError("amount_step must not be negative for arithmetic amount mode.")
    if config.amount_mode == AmountMode.GEOMETRIC and config.amount_ratio <= 0:
        raise ValueError("amount_ratio must be positive for geometric amount mode.")
    if config.scale_start_level <= 0:
        raise ValueError("scale_start_level must be positive.")
    if config.price_start_level <= 0:
        raise ValueError("price_start_level must be positive.")
    if config.retain_profit.multiplier <= 0:
        raise ValueError("retain_profit.multiplier must be positive.")


def round_price(value: float, digits: int) -> float:
    return round(value, digits)


def round_lot_shares(amount: float, price: float, lot_size: int) -> int:
    raw_shares = math.floor(amount / price)
    return (raw_shares // lot_size) * lot_size


def round_down_to_lot(shares: int, lot_size: int) -> int:
    return (shares // lot_size) * lot_size


def planned_amount_for_level(config: GridPlanConfig, zero_based_index: int) -> float:
    if config.amount_mode == AmountMode.EQUAL:
        return config.first_amount
    scale_index = max(0, zero_based_index - config.scale_start_level + 1)
    if config.amount_mode == AmountMode.ARITHMETIC:
        return config.first_amount + config.amount_step * scale_index
    if config.amount_mode == AmountMode.GEOMETRIC:
        return config.first_amount * (config.amount_ratio**scale_index)
    raise ValueError(f"Unsupported amount_mode: {config.amount_mode}")


def calc_fee(amount: float, fee_rate: float, min_fee: float) -> float:
    if amount <= 0:
        return 0.0
    return max(amount * fee_rate, min_fee)


def is_retain_profit_enabled(config: GridPlanConfig) -> bool:
    return config.strategy_version != "1.0" and config.retain_profit.enabled


def estimate_retain_profit_fields(
    shares: int,
    sell_exec_price: float,
    full_net_sell_amount: float,
    total_cost: float,
    config: GridPlanConfig,
) -> tuple[int, int, float, float, str]:
    if shares <= 0:
        return 0, 0, 0.0, 0.0, "no_position"
    if not is_retain_profit_enabled(config):
        return shares, 0, 0.0, full_net_sell_amount, "full_sell"

    full_profit = full_net_sell_amount - total_cost
    if full_profit <= 0:
        return shares, 0, 0.0, full_net_sell_amount, "full_sell_no_profit"

    target_retained_value = full_profit * config.retain_profit.multiplier
    max_retained_shares = max(shares - config.lot_size, 0)
    retained_shares = round_lot_shares(target_retained_value, sell_exec_price, config.lot_size)
    retained_shares = min(retained_shares, max_retained_shares)
    retained_shares = round_down_to_lot(max(retained_shares, 0), config.lot_size)
    sold_shares = shares - retained_shares
    retained_value = retained_shares * sell_exec_price
    recover_cost = sold_shares * sell_exec_price
    return sold_shares, retained_shares, retained_value, recover_cost, "retain_profit" if retained_shares else "full_sell"


def build_grid_plan(config: GridPlanConfig, price_context: PriceContext | None = None) -> GridPlan:
    validate_config(config)
    grid_step = config.first_price * config.grid_pct
    grid_count = math.ceil((config.first_price - config.bottom_price) / grid_step) + 1
    start_offset = config.price_start_level - 1
    levels: list[GridLevel] = []
    warnings: list[str] = []

    cumulative_cost = 0.0
    total_shares = 0
    total_invested = 0.0
    total_planned_amount = 0.0
    total_unused_amount = 0.0
    zero_share_levels = 0

    for i in range(start_offset, grid_count):
        level_index = i + 1
        buy_price_raw = config.first_price - grid_step * i
        if buy_price_raw <= 0:
            break

        sell_price_raw = config.first_price + grid_step if i == 0 else config.first_price - grid_step * (i - 1)
        buy_price = round_price(buy_price_raw, config.price_digits)
        sell_price = round_price(sell_price_raw, config.price_digits)
        planned_amount = planned_amount_for_level(config, i)
        buy_exec_price = buy_price * (1 + config.slippage_rate)
        sell_exec_price = sell_price * (1 - config.slippage_rate)
        shares = round_lot_shares(planned_amount, buy_exec_price, config.lot_size)
        actual_invested = shares * buy_exec_price
        unused_amount = planned_amount - actual_invested
        amount_usage_pct = actual_invested / planned_amount if planned_amount else 0.0
        buy_fee = calc_fee(actual_invested, config.fee_rate, config.min_fee)
        total_cost = actual_invested + buy_fee
        gross_sell_amount = shares * sell_exec_price
        sell_fee = calc_fee(gross_sell_amount, config.fee_rate, config.min_fee)
        net_sell_amount = gross_sell_amount - sell_fee
        expected_profit = net_sell_amount - total_cost
        expected_return_pct = expected_profit / total_cost if total_cost else 0.0
        expected_sold_shares, expected_retained_shares, expected_retained_value, expected_recover_cost, expected_sell_mode = (
            estimate_retain_profit_fields(
                shares=shares,
                sell_exec_price=sell_exec_price,
                full_net_sell_amount=net_sell_amount,
                total_cost=total_cost,
                config=config,
            )
        )
        level_warnings: list[str] = []
        if shares <= 0:
            zero_share_levels += 1
            level_warnings.append("planned_amount_below_one_lot")
        elif amount_usage_pct < 0.9:
            level_warnings.append("low_amount_usage_after_lot_rounding")
        if expected_profit <= 0 and shares > 0:
            level_warnings.append("non_positive_expected_profit_after_costs")
        warning_text = ";".join(level_warnings)
        for item in level_warnings:
            warnings.append(f"level {level_index}: {item}")

        cumulative_cost += total_cost
        total_shares += shares
        total_invested += actual_invested
        total_planned_amount += planned_amount
        total_unused_amount += max(unused_amount, 0.0)

        levels.append(
            GridLevel(
                grid_name=config.grid_name,
                level_index=level_index,
                buy_price=buy_price,
                sell_price=sell_price,
                grid_step=round_price(grid_step, config.price_digits),
                planned_amount=planned_amount,
                shares=shares,
                actual_invested=actual_invested,
                unused_amount=unused_amount,
                amount_usage_pct=amount_usage_pct,
                buy_fee=buy_fee,
                total_cost=total_cost,
                gross_sell_amount=gross_sell_amount,
                sell_fee=sell_fee,
                net_sell_amount=net_sell_amount,
                expected_profit=expected_profit,
                expected_return_pct=expected_return_pct,
                expected_sold_shares=expected_sold_shares,
                expected_retained_shares=expected_retained_shares,
                expected_retained_value=expected_retained_value,
                expected_recover_cost=expected_recover_cost,
                expected_sell_mode=expected_sell_mode,
                cumulative_cost=cumulative_cost,
                drawdown_from_first_pct=(config.first_price - buy_price) / config.first_price,
                covers_bottom=buy_price <= config.bottom_price,
                warning=warning_text,
            )
        )

    if not levels:
        raise ValueError("No valid grid levels generated.")

    market_value_at_bottom = total_shares * config.bottom_price
    total_cost_at_bottom = sum(level.total_cost for level in levels)
    floating_pnl_at_bottom = market_value_at_bottom - total_cost_at_bottom
    floating_pnl_pct = floating_pnl_at_bottom / total_cost_at_bottom if total_cost_at_bottom else 0.0
    average_cost = total_invested / total_shares if total_shares else 0.0

    summary = StressSummary(
        symbol=config.symbol,
        first_price=round_price(config.first_price, config.price_digits),
        bottom_price=round_price(config.bottom_price, config.price_digits),
        grid_pct=config.grid_pct,
        grid_step=round_price(grid_step, config.price_digits),
        grid_count=len(levels),
        max_capital_required=total_cost_at_bottom,
        total_shares_at_bottom=total_shares,
        average_cost=average_cost,
        market_value_at_bottom=market_value_at_bottom,
        floating_pnl_at_bottom=floating_pnl_at_bottom,
        floating_pnl_pct_at_bottom=floating_pnl_pct,
        last_buy_price=levels[-1].buy_price,
        covers_bottom=levels[-1].buy_price <= config.bottom_price,
        bottom_over_coverage=max(config.bottom_price - levels[-1].buy_price, 0.0),
        total_planned_amount=total_planned_amount,
        total_actual_invested=total_invested,
        total_unused_amount=total_unused_amount,
        zero_share_levels=zero_share_levels,
        warning_count=len(warnings),
    )
    return GridPlan(config=config, levels=levels, summary=summary, price_context=price_context, warnings=warnings)


def combine_grid_plans(plans: list[GridPlan]) -> GridPlan:
    if not plans:
        raise ValueError("No grid plans to combine.")

    base = plans[0]
    levels = [level for plan in plans for level in plan.levels]
    warnings = [warning for plan in plans for warning in (plan.warnings or [])]
    total_cost_at_bottom = sum(plan.summary.max_capital_required for plan in plans)
    total_shares = sum(plan.summary.total_shares_at_bottom for plan in plans)
    total_actual_invested = sum(plan.summary.total_actual_invested for plan in plans)
    market_value_at_bottom = sum(plan.summary.market_value_at_bottom for plan in plans)
    floating_pnl_at_bottom = market_value_at_bottom - total_cost_at_bottom
    average_cost = total_actual_invested / total_shares if total_shares else 0.0
    last_buy_price = min(plan.summary.last_buy_price for plan in plans)

    summary = StressSummary(
        symbol=base.summary.symbol,
        first_price=base.summary.first_price,
        bottom_price=base.summary.bottom_price,
        grid_pct=0.0,
        grid_step=0.0,
        grid_count=len(levels),
        max_capital_required=total_cost_at_bottom,
        total_shares_at_bottom=total_shares,
        average_cost=average_cost,
        market_value_at_bottom=market_value_at_bottom,
        floating_pnl_at_bottom=floating_pnl_at_bottom,
        floating_pnl_pct_at_bottom=floating_pnl_at_bottom / total_cost_at_bottom if total_cost_at_bottom else 0.0,
        last_buy_price=last_buy_price,
        covers_bottom=all(plan.summary.covers_bottom for plan in plans),
        bottom_over_coverage=min(plan.summary.bottom_over_coverage for plan in plans),
        total_planned_amount=sum(plan.summary.total_planned_amount for plan in plans),
        total_actual_invested=total_actual_invested,
        total_unused_amount=sum(plan.summary.total_unused_amount for plan in plans),
        zero_share_levels=sum(plan.summary.zero_share_levels for plan in plans),
        warning_count=len(warnings),
    )
    combined_config = GridPlanConfig(
        symbol=base.config.symbol,
        first_price=base.config.first_price,
        grid_pct=0.0,
        bottom_price=base.config.bottom_price,
        first_amount=base.config.first_amount,
        grid_name="multi",
        strategy_version="2.3",
        amount_mode=base.config.amount_mode,
        amount_step=base.config.amount_step,
        amount_ratio=base.config.amount_ratio,
        scale_start_level=base.config.scale_start_level,
        price_start_level=base.config.price_start_level,
        retain_profit=base.config.retain_profit,
        lot_size=base.config.lot_size,
        fee_rate=base.config.fee_rate,
        min_fee=base.config.min_fee,
        slippage_rate=base.config.slippage_rate,
        price_digits=base.config.price_digits,
    )
    return GridPlan(
        config=combined_config,
        levels=levels,
        summary=summary,
        price_context=base.price_context,
        warnings=warnings,
    )


def plan_to_frame(plan: GridPlan) -> pd.DataFrame:
    return pd.DataFrame([asdict(level) for level in plan.levels])


def summary_to_frame(plan: GridPlan) -> pd.DataFrame:
    row = asdict(plan.summary)
    if plan.price_context is not None:
        row.update({f"price_context_{key}": value for key, value in asdict(plan.price_context).items()})
    return pd.DataFrame([row])


def warnings_to_frame(plan: GridPlan) -> pd.DataFrame:
    return pd.DataFrame([{"warning": warning} for warning in (plan.warnings or [])])


def render_markdown_report(plan: GridPlan) -> str:
    summary = plan.summary
    context = plan.price_context
    lines = [
        "# 网格计划报告",
        "",
        "## 压力测试摘要",
        "",
        f"- 标的代码 (symbol): {summary.symbol or '-'}",
        f"- 首网买入价格 (first_price): {summary.first_price:.4f}",
        f"- 压力测试底部价格 (bottom_price): {summary.bottom_price:.4f}",
        f"- 网格比例 (grid_pct): {summary.grid_pct:.2%}",
        f"- 固定网格价差 (grid_step): {summary.grid_step:.4f}",
        f"- 网格数量 (grid_count): {summary.grid_count}",
        f"- 最大资金占用 (max_capital_required): {summary.max_capital_required:.2f}",
        f"- 跌到底部时的平均持仓成本 (average_cost): {summary.average_cost:.4f}",
        f"- 跌到底部时的浮动盈亏 (floating_pnl_at_bottom): {summary.floating_pnl_at_bottom:.2f}",
        f"- 跌到底部时的浮动盈亏比例 (floating_pnl_pct_at_bottom): {summary.floating_pnl_pct_at_bottom:.2%}",
        f"- 最后一网买入价格 (last_buy_price): {summary.last_buy_price:.4f}",
        f"- 是否覆盖预设底部 (covers_bottom): {summary.covers_bottom}",
        f"- 最后一网低于底部的覆盖空间 (bottom_over_coverage): {summary.bottom_over_coverage:.4f}",
        f"- 整手取整后未使用资金合计 (total_unused_amount): {summary.total_unused_amount:.2f}",
        f"- 买不到一手的网格数量 (zero_share_levels): {summary.zero_share_levels}",
        f"- 策略版本 (strategy_version): {plan.config.strategy_version}",
        f"- 投入金额模式 (amount_mode): {plan.config.amount_mode.value}",
        f"- 价格起始格 (price_start_level): {plan.config.price_start_level}",
        f"- 开始加码格 (scale_start_level): {plan.config.scale_start_level}",
        f"- 等差递增步长 (amount_step): {plan.config.amount_step:.3f}",
        f"- 等比递增倍率 (amount_ratio): {plan.config.amount_ratio:.3f}",
        f"- 留利润开关 (retain_profit.enabled): {is_retain_profit_enabled(plan.config)}",
        f"- 留利润倍数 (retain_profit.multiplier): {plan.config.retain_profit.multiplier:.3f}",
        "",
        "说明：网格价格采用固定价差，价差 = 首网买入价格 * 网格比例；压力测试假设价格一路下跌并触发全部网格买入。",
        "",
    ]
    if context is not None:
        lines.extend(
            [
                "## 首网价格区间统计",
                "",
                f"- 数据来源 (source): {context.source}",
                f"- 是否使用复权价格 (adjusted): {context.adjusted}",
                f"- 复权方式 (adjust_method): {context.adjust_method or '-'}",
                f"- 统计起始日期 (start_date): {context.start_date or '全部历史'}",
                f"- 统计结束日期 (end_date): {context.end_date or '最新可读数据'}",
                f"- 区间最高价 (period_high): {format_optional_number(context.period_high)}",
                f"- 区间最低价 (period_low): {format_optional_number(context.period_low)}",
                f"- 最新收盘价 (latest_close): {format_optional_number(context.latest_close)}",
                f"- 首网价格在历史收盘价中的分位 (first_price_close_percentile): {format_optional_pct(context.first_price_close_percentile)}",
                f"- 收盘价低于或等于首网的天数/比例 (close_below_first_days/close_below_first_pct): {format_optional_days_pct(context.close_below_first_days, context.close_below_first_pct)}",
                f"- 最低价触及或低于首网的天数/比例 (low_touch_first_days/low_touch_first_pct): {format_optional_days_pct(context.low_touch_first_days, context.low_touch_first_pct)}",
                f"- 首网相对区间高点的回撤 (drawdown_from_period_high_pct): {format_optional_pct(context.drawdown_from_period_high_pct)}",
                "",
                "说明：如果配置文件未指定 start_date/end_date，则默认使用该品种全部可读历史数据；历史统计使用复权后的 OHLC 价格。",
                "",
            ]
        )
    if plan.warnings:
        lines.extend(["## 风险提示", ""])
        lines.extend(f"- {warning}" for warning in plan.warnings)
        lines.append("")

    preview_cols = [
        "grid_name",
        "level_index",
        "buy_price",
        "sell_price",
        "planned_amount",
        "shares",
        "actual_invested",
        "expected_profit",
        "expected_return_pct",
        "expected_sold_shares",
        "expected_retained_shares",
        "expected_retained_value",
        "expected_sell_mode",
        "cumulative_cost",
        "warning",
    ]
    frame = plan_to_frame(plan)[preview_cols]
    lines.extend(
        [
            "## 网格明细",
            "",
            "说明：`planned_amount` 是计划投入金额，`actual_invested` 是按交易单位和滑点计算后的实际买入金额，`expected_profit` 已扣除买卖手续费。",
            "",
            frame_to_markdown(frame),
            "",
        ]
    )
    return "\n".join(lines)


def format_optional_number(value: float | None) -> str:
    return "-" if value is None else f"{value:.4f}"


def format_optional_pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.2%}"


def format_optional_days_pct(days: int | None, pct: float | None) -> str:
    if days is None or pct is None:
        return "-"
    return f"{days} 天 / {pct:.2%}"


def frame_to_markdown(frame: pd.DataFrame) -> str:
    headers = [str(col) for col in frame.columns]
    rows = [[format_markdown_cell(value) for value in row] for row in frame.itertuples(index=False, name=None)]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def format_markdown_cell(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    if value is None:
        return ""
    text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def export_plan(plan: GridPlan, output_dir: Path, basename: str, include_markdown: bool = True) -> tuple[Path, Path, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    levels_path = output_dir / f"{basename}_levels.csv"
    summary_path = output_dir / f"{basename}_summary.csv"
    report_path = output_dir / f"{basename}_report.md" if include_markdown else None
    plan_to_frame(plan).to_csv(levels_path, index=False, encoding="utf-8-sig", float_format=FLOAT_FORMAT)
    summary_to_frame(plan).to_csv(summary_path, index=False, encoding="utf-8-sig", float_format=FLOAT_FORMAT)
    if plan.warnings:
        warnings_to_frame(plan).to_csv(
            output_dir / f"{basename}_warnings.csv",
            index=False,
            encoding="utf-8-sig",
            float_format=FLOAT_FORMAT,
        )
    if report_path is not None:
        report_path.write_text(render_markdown_report(plan), encoding="utf-8")
    return levels_path, summary_path, report_path
