from __future__ import annotations

from fastapi import APIRouter

from backend.app.schemas.common import ApiResponse, error_response, ok_response
from backend.app.schemas.grid_v1 import BacktestRequest, GridV1Config, HistoryRequest, JsonDict
from backend.app.services.grid_v1_service import load_history_records, make_backtest_payload, make_plan_payload


router = APIRouter(prefix="/api/grid/v1", tags=["grid-v1"])


@router.post("/history", response_model=ApiResponse[JsonDict])
def history(request: HistoryRequest):
    try:
        payload = load_history_records(
            symbol=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
            adjust_method=request.adjust_method,
        )
        return ok_response(payload)
    except Exception as exc:
        return error_response(str(exc))


@router.post("/plan", response_model=ApiResponse[JsonDict])
def plan(config: GridV1Config):
    try:
        payload = make_plan_payload(config)
        return ok_response(payload, warnings=payload.get("warnings", []))
    except Exception as exc:
        return error_response(str(exc))


@router.post("/backtest", response_model=ApiResponse[JsonDict])
def backtest(request: BacktestRequest):
    try:
        payload = make_backtest_payload(request.config, initial_cash=request.initial_cash)
        return ok_response(payload, warnings=payload.get("warnings", []))
    except Exception as exc:
        return error_response(str(exc))

