from __future__ import annotations

from typing import Optional


def _risk_from_ratio(ratio: float) -> str:
    if ratio >= 1.0:
        return "critical"
    if ratio >= 0.8:
        return "high"
    if ratio >= 0.6:
        return "medium"
    return "low"


def _format_pct(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    return f"{value:.0%}" if value <= 1 else f"{value:.1f}"


def explain_decision(
    zone_id: str,
    action: str,
    demand_kw: float,
    grid_kw: float,
    occupancy: str,
    load_ratio: Optional[float] = None,
    risk_level: Optional[str] = None,
    suggested_window: Optional[str] = None,
    infrastructure_recommendation: Optional[str] = None,
    station_pressure: Optional[float] = None,
    spillover_risk: Optional[float] = None,
    growth_score: Optional[float] = None,
    queue_risk: Optional[float] = None,
) -> str:
    """
    Generate a clear, operator-friendly explanation for BESCOM.

    Backward compatible with the existing routes.py call, but can also be used
    with richer inputs for stronger explanations.
    """
    if load_ratio is None:
        load_ratio = demand_kw / max(grid_kw, 1)

    if risk_level is None:
        risk_level = _risk_from_ratio(load_ratio)

    parts = [
        f"Zone {zone_id} is marked {action} because predicted demand is {demand_kw:.1f} kW",
        f"against grid headroom of {grid_kw:.1f} kW (load ratio {load_ratio:.2f}, risk {risk_level}).",
        f"Current station state is {occupancy}.",
    ]

    if station_pressure is not None:
        parts.append(f"Station pressure is {_format_pct(station_pressure)}.")
    if spillover_risk is not None:
        parts.append(f"Spillover risk is {_format_pct(spillover_risk)}.")
    if growth_score is not None:
        parts.append(f"Growth score is {_format_pct(growth_score)}.")
    if queue_risk is not None:
        parts.append(f"Queue risk is {_format_pct(queue_risk)}.")

    if suggested_window:
        parts.append(f"Suggested charging window: {suggested_window}.")
    if infrastructure_recommendation:
        parts.append(f"Infrastructure recommendation: {infrastructure_recommendation}.")

    if action == "DEFER":
        parts.append("Peak charging should be shifted away from this zone to reduce grid stress.")
    elif action == "ABSORB":
        parts.append("This zone has spare headroom and can absorb additional charging safely.")
    elif action == "BUILD":
        parts.append("Demand growth and congestion indicate a strong need for new charging capacity.")
    else:
        parts.append("This zone should be monitored closely before the next peak window.")

    return " ".join(parts)