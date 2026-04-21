from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    ok: bool
    data: T | None = None
    warnings: list[str] = []
    errors: list[str] = []


def ok_response(data: T, warnings: list[str] | None = None) -> ApiResponse[T]:
    return ApiResponse(ok=True, data=data, warnings=warnings or [], errors=[])


def error_response(message: str) -> ApiResponse[None]:
    return ApiResponse(ok=False, data=None, warnings=[], errors=[message])

