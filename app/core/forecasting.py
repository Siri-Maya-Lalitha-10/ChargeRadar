from __future__ import annotations

import hashlib
import math
from typing import Optional

import pandas as pd


def _stable_seed(*parts: object) -> int:
    """
    Stable seed so the same zone/hour/day/scenario always produces the same result.
    This keeps the demo consistent and avoids random jumps.
    """
    raw = "|".join(map(str, parts)).encode("utf-8")
    digest = hashlib.md5(raw).hexdigest()
    return int(digest[:8], 16)


def _is_weekend(day: int) -> bool:
    return (day % 7) in (5, 6)


def _capacity_base(zone_type: str, grid_capacity_kw: float) -> float:
    """
    Base demand anchored to capacity so peak periods can realistically
    reach high-load conditions.
    """
    zone_type = (zone_type or "").lower()
    ratio_map = {
        "residential": 0.22,
        "commercial": 0.26,
        "corridor": 0.24,
        "mixed": 0.23,
    }
    ratio = ratio_map.get(zone_type, 0.22)
    return grid_capacity_kw * ratio


def _time_multiplier(zone_type: str, hour: int) -> float:
    """
    Stronger time-of-day shape so the demo clearly shows peak stress.
    """
    zone_type = (zone_type or "").lower()

    if zone_type == "residential":
        if 6 <= hour <= 9:
            return 0.90
        if 18 <= hour <= 22:
            return 3.20
        if hour >= 23 or hour <= 4:
            return 0.40
        return 0.95

    if zone_type == "commercial":
        if 10 <= hour <= 16:
            return 2.55
        if 7 <= hour <= 9:
            return 1.25
        if 18 <= hour <= 21:
            return 0.70
        return 0.55

    if zone_type == "corridor":
        if 7 <= hour <= 10 or 17 <= hour <= 21:
            return 2.30
        if hour >= 22 or hour <= 5:
            return 0.42
        return 0.78

    # mixed
    if 7 <= hour <= 10:
        return 1.18
    if 16 <= hour <= 21:
        return 1.90
    if hour >= 23 or hour <= 5:
        return 0.55
    return 0.92


def _scenario_multiplier(zone_type: str, hour: int, scenario: str) -> float:
    """
    Hidden demo control. Keeps the UI clean while allowing peak demos.
    """
    zone_type = (zone_type or "").lower()
    scenario = (scenario or "normal").lower()

    if scenario == "residential_peak" and zone_type == "residential" and 18 <= hour <= 22:
        return 1.35

    if scenario == "commercial_peak" and zone_type == "commercial" and 10 <= hour <= 16:
        return 1.25

    if scenario == "corridor_burst" and zone_type == "corridor" and (7 <= hour <= 10 or 17 <= hour <= 21):
        return 1.30

    if scenario == "underutilized_night" and (hour >= 23 or hour <= 5):
        return 1.20

    if scenario == "event_spike" and hour in (18, 19, 20):
        return 1.45

    return 1.0


def _growth_multiplier(day: int, growth_rate: float, weekend: bool) -> float:
    """
    Growth over days + weekend lift.
    """
    day_growth = 1.0 + (day * growth_rate * 1.0)
    weekend_boost = 1.14 if weekend else 1.0
    return day_growth * weekend_boost


def _density_factor(ev_density: float, station_density: float) -> float:
    """
    EV density and station density affect how much demand concentrates.
    """
    ev_part = 0.78 + (ev_density / 150.0)
    station_part = 0.96 + min(0.22, station_density * 0.03)
    return min(1.65, ev_part * station_part)


def _grid_pressure_factor(grid_load_kw: Optional[float], grid_capacity_kw: float) -> float:
    """
    If the grid is already stressed, some demand gets pushed away.
    """
    if grid_load_kw is None or grid_capacity_kw <= 0:
        return 1.0

    load_ratio = max(0.0, min(1.5, float(grid_load_kw) / grid_capacity_kw))
    if load_ratio <= 0.75:
        return 1.0
    if load_ratio <= 0.90:
        return 0.97
    if load_ratio <= 1.05:
        return 0.92
    return 0.86


def forecast_zone_demand(
    zone_row: pd.Series,
    hour: int,
    day: int,
    scenario: str = "normal",
    grid_load_kw: Optional[float] = None,
) -> float:
    """
    Predict EV charging demand for one zone in kW.
    This is the main demand engine used by the backend.
    """
    zone_type = str(zone_row["zone_type"])
    ev_density = float(zone_row.get("ev_density", 100))
    station_density = float(zone_row.get("station_density", 3))
    growth_rate = float(zone_row.get("growth_rate", 0.04))
    grid_capacity = float(zone_row.get("grid_capacity_kw", 500))

    base = _capacity_base(zone_type, grid_capacity)
    time_factor = _time_multiplier(zone_type, hour)
    growth_factor = _growth_multiplier(day, growth_rate, _is_weekend(day))
    scenario_factor = _scenario_multiplier(zone_type, hour, scenario)
    density_factor = _density_factor(ev_density, station_density)
    grid_factor = _grid_pressure_factor(grid_load_kw, grid_capacity)

    seed = _stable_seed(zone_row["zone_id"], hour, day, scenario)
    noise = math.sin(seed % 1000) * 8.0  # stable, small variation

    demand = base * time_factor * growth_factor * scenario_factor * density_factor * grid_factor + noise

    # Keep the output realistic but allow visible peak stress.
    # Peak periods should be able to cross into high-load territory.
    demand = max(0.0, demand)
    return round(demand, 2)


def forecast_zone_risk(
    zone_row: pd.Series,
    hour: int,
    day: int,
    scenario: str = "normal",
    grid_load_kw: Optional[float] = None,
) -> dict:
    """
    Optional helper for risk scoring and buckets.
    """
    demand = forecast_zone_demand(
        zone_row=zone_row,
        hour=hour,
        day=day,
        scenario=scenario,
        grid_load_kw=grid_load_kw,
    )

    capacity = float(zone_row["grid_capacity_kw"])
    ratio = demand / capacity if capacity > 0 else 0.0

    if ratio >= 1.0:
        risk = "critical"
    elif ratio >= 0.8:
        risk = "high"
    elif ratio >= 0.55:
        risk = "medium"
    else:
        risk = "low"

    return {
        "predicted_demand_kw": demand,
        "load_ratio": round(ratio, 3),
        "risk_level": risk,
    }