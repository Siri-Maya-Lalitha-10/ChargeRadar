from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ZoneDecision:
    action: str
    risk_level: str
    load_ratio: float
    score: float
    suggested_charging_window: str
    infrastructure_recommendation: str
    explanation: str


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _risk_from_ratio(ratio: float) -> str:
    if ratio >= 1.0:
        return "critical"
    if ratio >= 0.82:
        return "high"
    if ratio >= 0.62:
        return "medium"
    return "low"


def _off_peak_window() -> str:
    return "22:00 - 06:00"


def get_zone_decision(
    demand_kw: float,
    grid_capacity_kw: float,
    growth_score: float,
    station_pressure: float = 0.0,
    spillover_risk: float = 0.0,
    demand_trend: float = 0.0,
    station_density: Optional[float] = None,
    scenario: str = "normal",
) -> ZoneDecision:
    """
    Convert demand + growth + congestion signals into one operational decision.
    This version is tuned to make peak-stress and infrastructure gaps more visible
    in the demo.
    """
    capacity = max(grid_capacity_kw, 1.0)
    load_ratio = demand_kw / capacity

    scenario = (scenario or "normal").lower()

    scenario_boost = 0.0
    if scenario in {"residential_peak", "corridor_burst"}:
        scenario_boost = 0.07
    elif scenario in {"commercial_peak", "event_spike"}:
        scenario_boost = 0.05
    elif scenario == "underutilized_night":
        scenario_boost = -0.02

    risk_level = _risk_from_ratio(load_ratio)

    # Composite stress score: current load + growth + station congestion + spillover
    composite_pressure = (
        0.50 * _clamp(load_ratio, 0.0, 1.5)
        + 0.20 * _clamp(growth_score, 0.0, 1.0)
        + 0.16 * _clamp(station_pressure, 0.0, 1.0)
        + 0.10 * _clamp(spillover_risk, 0.0, 1.0)
        + 0.04 * _clamp(demand_trend, -1.0, 1.0)
        + scenario_boost
    )

    # Make infra gaps matter more.
    low_density = station_density is not None and station_density <= 3

    # ----------------------------
    # Decision rules
    # ----------------------------
    # 1) DEFER: clear peak stress
    if (
        load_ratio >= 0.80
        or station_pressure >= 0.78
        or spillover_risk >= 0.68
        or (risk_level in {"high", "critical"} and composite_pressure >= 0.77)
    ):
        action = "DEFER"
        suggested_window = _off_peak_window()
        if scenario in {"residential_peak", "corridor_burst"}:
            suggested_window = "22:00 - 06:00 (preferred off-peak window)"
        infrastructure = "OPTIMIZE_EXISTING"
        explanation = (
            f"Predicted demand is too close to grid capacity for safe peak charging. "
            f"Load ratio is {load_ratio:.2f}, station pressure is {station_pressure:.2f}, "
            f"spillover risk is {spillover_risk:.2f}. Shift charging to off-peak hours."
        )

    # 2) BUILD: growth + limited coverage + sustained stress
    elif (
        growth_score >= 0.62
        and load_ratio >= 0.52
        and (
            spillover_risk >= 0.40
            or station_pressure >= 0.50
            or low_density
        )
    ):
        action = "BUILD"
        suggested_window = "Plan new infrastructure; keep current charging flexible"
        infrastructure = (
            "BUILD_NEW_STATION"
            if low_density
            else "ADD_CAPACITY_OR_BALANCE_LOAD"
        )
        explanation = (
            f"This zone shows sustained growth ({growth_score:.2f}) with rising load "
            f"({load_ratio:.2f}) and limited current charging coverage. "
            f"It is a strong candidate for new charging infrastructure."
        )

    # 3) ABSORB: spare headroom
    elif load_ratio <= 0.50 and station_pressure <= 0.45 and spillover_risk <= 0.35:
        action = "ABSORB"
        suggested_window = "Immediate / flexible"
        infrastructure = "ABSORB_EXISTING_LOAD"
        explanation = (
            f"This zone has spare grid headroom. Load ratio is {load_ratio:.2f} and "
            f"station pressure is low, so it can absorb more charging safely."
        )

    # 4) MONITOR: in-between zones
    else:
        action = "MONITOR"
        suggested_window = "Observe next peak window"
        infrastructure = "MONITOR_AND_REVIEW"
        explanation = (
            f"This zone is not critical yet, but it is not fully safe either. "
            f"Load ratio is {load_ratio:.2f}, growth score is {growth_score:.2f}, "
            f"and spillover risk is {spillover_risk:.2f}. Keep monitoring."
        )

    # Fine-tune: quickly escalating zones should defer rather than wait
    if action == "MONITOR" and demand_trend >= 0.32 and load_ratio >= 0.60:
        action = "DEFER"
        suggested_window = _off_peak_window()
        infrastructure = "OPTIMIZE_EXISTING"
        explanation += " Demand is rising quickly, so deferral is safer than waiting."

    # Fine-tune: rapid growth with low density should become BUILD more easily
    if (
        action == "MONITOR"
        and growth_score >= 0.70
        and low_density
        and load_ratio >= 0.55
    ):
        action = "BUILD"
        suggested_window = "Plan new infrastructure; keep current charging flexible"
        infrastructure = "BUILD_NEW_STATION"
        explanation = (
            f"This zone is growing quickly and has limited charger coverage. "
            f"It should be prioritized for infrastructure planning."
        )

    score = _clamp(composite_pressure, 0.0, 1.5)

    return ZoneDecision(
        action=action,
        risk_level=risk_level,
        load_ratio=round(load_ratio, 3),
        score=round(score, 3),
        suggested_charging_window=suggested_window,
        infrastructure_recommendation=infrastructure,
        explanation=explanation,
    )


def classify_zone(demand_kw: float, grid_capacity_kw: float, growth_score: float) -> str:
    """
    Backward-compatible wrapper for your current routes.py.
    Returns only the action string so nothing breaks.
    """
    return get_zone_decision(
        demand_kw=demand_kw,
        grid_capacity_kw=grid_capacity_kw,
        growth_score=growth_score,
    ).action