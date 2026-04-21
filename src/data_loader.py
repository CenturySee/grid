from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from .models import PriceContext


TDX_ROOTS = {
    "sh": Path("C:/new_tdx/vipdoc/sh"),
    "sz": Path("C:/new_tdx/vipdoc/sz"),
    "bj": Path("C:/new_tdx/vipdoc/bj"),
}


@dataclass(frozen=True)
class SymbolInfo:
    market: str
    code: str

    @property
    def symbol(self) -> str:
        return f"{self.market}{self.code}"


def parse_symbol(symbol: str) -> SymbolInfo:
    normalized = symbol.lower().strip()
    if len(normalized) == 8 and normalized[:2] in TDX_ROOTS:
        return SymbolInfo(market=normalized[:2], code=normalized[2:])
    if len(normalized) == 6 and normalized.isdigit():
        if normalized.startswith(("5", "6", "9")):
            return SymbolInfo(market="sh", code=normalized)
        if normalized.startswith(("0", "1", "2", "3")):
            return SymbolInfo(market="sz", code=normalized)
        if normalized.startswith(("4", "8")):
            return SymbolInfo(market="bj", code=normalized)
    raise ValueError("symbol must look like sh510300, sz159915, bjxxxxx, or a 6 digit code.")


def load_tdx_daily_history(symbol: str) -> pd.DataFrame:
    """Load local Tongdaxin daily data with pytdx.

    The source files are raw/unadjusted. Use apply_adjust_factor before using
    historical high/low statistics for grid planning.
    """

    info = parse_symbol(symbol)
    try:
        from pytdx.reader import TdxDailyBarReader
    except ImportError as exc:
        raise ImportError("pytdx is required to read local Tongdaxin daily data.") from exc

    root = TDX_ROOTS[info.market]
    file_path = root / "lday" / f"{info.market}{info.code}.day"
    if not file_path.exists():
        raise FileNotFoundError(f"Tongdaxin daily file not found: {file_path}")

    reader = TdxDailyBarReader()
    df = reader.get_df(str(file_path)).reset_index()
    if "datetime" in df.columns:
        df = df.rename(columns={"datetime": "date"})
    if "date" not in df.columns and "index" in df.columns:
        df = df.rename(columns={"index": "date"})
    df["date"] = pd.to_datetime(df["date"])
    df["symbol"] = info.symbol
    return df.sort_values("date").reset_index(drop=True)


def load_adjust_factor(symbol: str, adjust_method: Literal["forward", "backward"] = "forward") -> pd.DataFrame:
    """Load adjustment factors through opentdx.stock_adjust_factor_by_xdxr.

    This function intentionally keeps a narrow contract because opentdx package
    APIs may differ by installation. It accepts either a DataFrame result or a
    list/dict result and normalizes date/factor columns.
    """

    info = parse_symbol(symbol)
    try:
        import opentdx
    except ImportError as exc:
        raise ImportError("opentdx is required to fetch xdxr adjustment factors.") from exc

    if hasattr(opentdx, "stock_adjust_factor_by_xdxr"):
        raw = opentdx.stock_adjust_factor_by_xdxr(info.symbol)
    elif hasattr(opentdx, "TdxClient") and hasattr(opentdx, "MARKET"):
        market_map = {
            "sh": opentdx.MARKET.SH,
            "sz": opentdx.MARKET.SZ,
            "bj": opentdx.MARKET.BJ,
        }
        raw = opentdx.TdxClient().stock_adjust_factor_by_xdxr(market_map[info.market], info.code, count=0)
    else:
        raise AttributeError("opentdx stock_adjust_factor_by_xdxr API is not available.")

    df = raw if isinstance(raw, pd.DataFrame) else pd.DataFrame(raw)
    if df.empty:
        raise ValueError(f"No adjustment factor rows returned for {info.symbol}.")

    date_col = next((col for col in ("date", "datetime", "trade_date") if col in df.columns), None)
    preferred_factor_cols = (
        ("qfq_factor", "factor", "adjust_factor", "adj_factor")
        if adjust_method == "forward"
        else ("hfq_factor", "factor", "adjust_factor", "adj_factor")
    )
    factor_col = next((col for col in preferred_factor_cols if col in df.columns), None)
    if date_col is None or factor_col is None:
        raise ValueError(f"Cannot identify date/factor columns in adjustment factor data: {list(df.columns)}")

    result = df[[date_col, factor_col]].rename(columns={date_col: "date", factor_col: "factor"}).copy()
    result["date"] = pd.to_datetime(result["date"])
    result["factor"] = pd.to_numeric(result["factor"], errors="coerce")
    result = result.dropna(subset=["factor"]).sort_values("date").reset_index(drop=True)
    return result


def apply_adjust_factor(
    history: pd.DataFrame,
    factors: pd.DataFrame,
    method: Literal["forward", "backward"] = "forward",
) -> pd.DataFrame:
    """Apply xdxr factors to raw OHLC prices.

    `forward` keeps the latest price scale by normalizing factors to the latest
    factor. `backward` keeps the earliest price scale.
    """

    if history.empty:
        return history.copy()
    if factors.empty:
        raise ValueError("factors must not be empty.")

    df = history.sort_values("date").copy()
    factors = factors.sort_values("date")[["date", "factor"]].copy()
    merged = pd.merge_asof(df, factors, on="date", direction="backward")
    merged["factor"] = merged["factor"].ffill().bfill()

    if method == "forward":
        base_factor = float(merged["factor"].iloc[-1])
    elif method == "backward":
        base_factor = float(merged["factor"].iloc[0])
    else:
        raise ValueError("method must be 'forward' or 'backward'.")

    ratio = merged["factor"] / base_factor
    adjusted = merged.copy()
    for col in ("open", "high", "low", "close"):
        if col in adjusted.columns:
            adjusted[col] = adjusted[col].astype(float) * ratio
    adjusted["adjust_factor"] = merged["factor"]
    adjusted["adjust_method"] = method
    return adjusted


def load_adjusted_daily_history(symbol: str, adjust_method: Literal["forward", "backward"] = "forward") -> pd.DataFrame:
    raw_history = load_tdx_daily_history(symbol)
    factors = load_adjust_factor(symbol, adjust_method=adjust_method)
    return apply_adjust_factor(raw_history, factors, method=adjust_method)


def filter_history(
    history: pd.DataFrame,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    df = history.copy()
    if start_date:
        df = df[df["date"] >= pd.Timestamp(start_date)]
    if end_date:
        df = df[df["date"] <= pd.Timestamp(end_date)]
    if df.empty:
        raise ValueError("No history rows after date filtering.")
    return df.reset_index(drop=True)


def build_price_context(
    history: pd.DataFrame,
    first_price: float,
    source: str,
    adjusted: bool,
    adjust_method: str | None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> PriceContext:
    if history.empty:
        return PriceContext(
            source=source,
            adjusted=adjusted,
            adjust_method=adjust_method,
            start_date=start_date,
            end_date=end_date,
        )

    df = history.sort_values("date").reset_index(drop=True)
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    low = pd.to_numeric(df["low"], errors="coerce").dropna()
    high = pd.to_numeric(df["high"], errors="coerce").dropna()
    total_days = len(df)
    close_below_days = int((df["close"] <= first_price).sum())
    low_touch_days = int((df["low"] <= first_price).sum())
    period_high = float(high.max()) if not high.empty else None
    period_low = float(low.min()) if not low.empty else None
    latest_close = float(close.iloc[-1]) if not close.empty else None
    percentile = float((close <= first_price).mean()) if not close.empty else None
    drawdown = (period_high - first_price) / period_high if period_high and period_high > 0 else None

    return PriceContext(
        source=source,
        adjusted=adjusted,
        adjust_method=adjust_method,
        start_date=start_date,
        end_date=end_date,
        period_high=period_high,
        period_low=period_low,
        latest_close=latest_close,
        first_price_close_percentile=percentile,
        close_below_first_days=close_below_days,
        close_below_first_pct=close_below_days / total_days if total_days else None,
        low_touch_first_days=low_touch_days,
        low_touch_first_pct=low_touch_days / total_days if total_days else None,
        drawdown_from_period_high_pct=drawdown,
    )
