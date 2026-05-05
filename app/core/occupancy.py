from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StationState:
    occupancy: float
    status: str
    time_to_full_minutes: int
    time_to_free_minutes: int
    queue_risk: float = 0.0
    occupancy_trend: str = "stable"
    utilization_ratio: float = 0.0
    estimated_wait_minutes: int = 0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _station_type_factor(station_type: str) -> float:
    """
    Fast stations absorb load better.
    Slow stations saturate more easily.
    """
    station_type = (station_type or "standard").lower()
    if station_type == "fast":
        return 0.78
    if station_type == "slow":
        return 1.18
    return 1.00


def _status_from_occupancy(occ: float) -> str:
    if occ >= 0.95:
        return "full"
    if occ >= 0.78:
        return "near_full"
    if occ >= 0.38:
        return "engaged"
    return "free"


def _trend_from_delta(delta: float) -> str:
    if delta >= 0.14:
        return "rising_fast"
    if delta >= 0.06:
        return "rising"
    if delta <= -0.10:
        return "falling_fast"
    if delta <= -0.04:
        return "falling"
    return "stable"


def compute_station_state(
    chargers: int,
    power_per_charger_kw: int,
    incoming_demand_kw: float,
    current_occupancy: float,
    station_type: str = "standard",
    utilization_base: float = 0.35,
    nearby_pressure: float = 0.0,
    scenario: str = "normal",
) -> StationState:
    """
    Estimate current station state from demand and station capacity.

    The logic is intentionally tuned to show realistic congestion during peak hours.
    """
    station_capacity_kw = max(chargers * power_per_charger_kw, 1)
    load_ratio = incoming_demand_kw / station_capacity_kw

    type_factor = _station_type_factor(station_type)
    scenario = (scenario or "normal").lower()

    # Scenario tuning for stronger demo behavior
    if scenario == "residential_peak":
        scenario_factor = 1.22
    elif scenario == "corridor_burst":
        scenario_factor = 1.28
    elif scenario == "commercial_peak":
        scenario_factor = 1.12
    elif scenario == "underutilized_night":
        scenario_factor = 0.82
    elif scenario == "event_spike":
        scenario_factor = 1.18
    else:
        scenario_factor = 1.0

    baseline = _clamp(utilization_base, 0.0, 1.0)
    current_occupancy = _clamp(current_occupancy, 0.0, 1.0)
    nearby_pressure = _clamp(nearby_pressure, 0.0, 1.0)

    # Demand pressure creates occupancy growth
    pressure = load_ratio * type_factor * scenario_factor

    # Nearby pressure matters more now — spillover should be visible
    occupancy_push = pressure * 0.55 + nearby_pressure * 0.18

    # Very low load allows some release
    if load_ratio < 0.18:
        recovery = (0.18 - load_ratio) * 0.14
    else:
        recovery = 0.0

    new_occupancy = _clamp(
        baseline
        + (current_occupancy - baseline) * 0.45
        + occupancy_push
        - recovery,
        0.0,
        1.0,
    )

    status = _status_from_occupancy(new_occupancy)
    delta = new_occupancy - current_occupancy
    occupancy_trend = _trend_from_delta(delta)

    # Queue risk rises faster when occupancy and demand are both high
    queue_risk = _clamp(
        0.10
        + (0.60 * new_occupancy)
        + (0.25 * min(1.5, load_ratio))
        + (0.15 * nearby_pressure),
        0.0,
        1.0,
    )

    # Estimated wait time: more visible in congested cases
    estimated_wait_minutes = int(
        round(
            max(
                0.0,
                ((queue_risk - 0.30) * 55)
                + max(0.0, (new_occupancy - 0.72) * 35)
            )
        )
    )

    # Time to full: aggressively decreases when pressure rises
    if status == "full":
        time_to_full = 1
    elif load_ratio <= 0.02 and new_occupancy < 0.30:
        time_to_full = 999
    else:
        pressure_rate = max(0.04, min(1.00, load_ratio * 0.75 + nearby_pressure * 0.18))
        remaining = max(0.0, 1.0 - new_occupancy)
        time_to_full = max(1, int(round((remaining / pressure_rate) * 60)))

    # Time to free: depends on station type and congestion
    base_release = {
        "fast": 10,
        "standard": 18,
        "slow": 26,
    }.get((station_type or "standard").lower(), 18)

    if status == "full":
        time_to_free = max(10, int(round(base_release * (1.20 + queue_risk * 0.80))))
    elif status == "near_full":
        time_to_free = max(8, int(round(base_release * (0.95 + queue_risk * 0.60))))
    elif status == "engaged":
        time_to_free = max(5, int(round(base_release * 0.70)))
    else:
        time_to_free = 0

    return StationState(
        occupancy=round(new_occupancy, 2),
        status=status,
        time_to_full_minutes=time_to_full,
        time_to_free_minutes=time_to_free,
        queue_risk=round(queue_risk, 2),
        occupancy_trend=occupancy_trend,
        utilization_ratio=round(new_occupancy, 2),
        estimated_wait_minutes=estimated_wait_minutes,
    )