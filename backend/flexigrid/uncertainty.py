"""One-sided split-conformal reserves from held-out whole-horizon errors.

This module does not train a forecaster. Forecasts must be generated without
using their corresponding outcomes. Coverage needs exchangeable calibration
and deployment blocks; arbitrary time-series drift does not satisfy that.
"""
from __future__ import annotations
import math
from typing import Annotated
import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from .planning import Finite


class CalibrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    forecasts_kw: list[Annotated[list[Finite], Field(min_length=1, max_length=192)]] = Field(min_length=1, max_length=5000)
    actuals_kw: list[Annotated[list[Finite], Field(min_length=1, max_length=192)]] = Field(min_length=1, max_length=5000)
    alpha: Finite = Field(default=0.1, gt=0, lt=1)


def calibrate_reserve(request: CalibrationRequest) -> dict:
    """Quantile of max positive error per block, with finite-sample correction."""
    for values in (request.forecasts_kw, request.actuals_kw):
        widths = {len(row) for row in values}
        if len(widths) != 1 or not 1 <= next(iter(widths)) <= 192:
            raise ValueError("blocks must share a horizon of 1 to 192 slots")
    forecast = np.asarray(request.forecasts_kw, dtype=float)
    actual = np.asarray(request.actuals_kw, dtype=float)
    if forecast.shape != actual.shape:
        raise ValueError("forecasts and actuals must have the same shape")
    if not np.isfinite(forecast).all() or not np.isfinite(actual).all():
        raise ValueError("calibration data must be finite")
    if np.any(forecast < 0) or np.any(actual < 0):
        raise ValueError("background consumption must be nonnegative")
    scores = np.maximum(0, (actual - forecast).max(axis=1))
    n = len(scores)
    rank = math.ceil((n + 1) * (1 - request.alpha))
    if rank > n:
        raise ValueError("insufficient calibration blocks for a finite reserve at this alpha")
    reserve = float(np.sort(scores)[rank - 1])
    return {"reserve_kw": [reserve] * forecast.shape[1],
            "calibration_blocks": n, "quantile_rank": rank, "alpha": request.alpha,
            "method": "one-sided-block-max-split-conformal",
            "coverage_scope": "marginal whole-block under exchangeable blocks",
            "assumptions": ["out-of-sample forecasts with a fixed independently trained model",
                            "exchangeable calibration and future blocks",
                            "same horizon, units and forecasting procedure"],
            "warning": "Not a per-household, conditional, drift-robust or physical safety guarantee."}
