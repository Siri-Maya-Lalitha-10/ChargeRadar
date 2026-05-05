from __future__ import annotations

from typing import Optional

import pandas as pd


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _get_state_value(state, key: str, default=None):
    """
    Supports either:
    - dict state
    - dataclass/object state
    """
    if state is None:
        return default
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


def _station_type_factor(station_type: str) -> float:
    station_type = (station_type or "standard").lower()
    if station_type == "fast":
        return 1.22
    if station_type == "slow":
        return 0.88
    return 1.00


def _spillover_ratio(
    source_pressure: float,
    scenario: str = "normal",
) -> float:
    """
    Stronger spillover so peak behavior becomes visible in demo.
    """
    scenario = (scenario or "normal").lower()

    # Base spill
    ratio = 0.18

    # Pressure-based increase
    ratio += max(0.0, source_pressure - 0.60) * 0.14
    ratio += max(0.0, source_pressure - 1.00) * 0.10

    # Scenario boost
    if scenario in {"residential_peak", "corridor_burst"}:
        ratio += 0.06
    elif scenario == "commercial_peak":
        ratio += 0.04
    elif scenario == "event_spike":
        ratio += 0.05
    elif scenario == "underutilized_night":
        ratio -= 0.05

    return _clamp(ratio, 0.15, 0.55)


def _availability_factor(
    target_row: pd.Series,
    target_state=None,
    source_zone_type: Optional[str] = None,
    target_zone_type: Optional[str] = None,
) -> float:
    """
    Higher = better candidate for absorbing spillover.
    """
    base_utilization = float(target_row.get("utilization_base", 0.35))
    occupancy = float(_get_state_value(target_state, "occupancy", base_utilization))
    status = str(_get_state_value(target_state, "status", "unknown")).lower()
    queue_risk = float(_get_state_value(target_state, "queue_risk", 0.25))

    if status == "full":
        state_factor = 0.04
    elif status == "near_full":
        state_factor = 0.28
    elif status == "engaged":
        state_factor = 0.84
    elif status == "free":
        state_factor = 1.20
    else:
        state_factor = 1.05 - (occupancy * 0.45) - (queue_risk * 0.20)

    zone_match = 1.0
    if source_zone_type and target_zone_type and source_zone_type == target_zone_type:
        zone_match = 1.10

    return _clamp(state_factor * zone_match, 0.05, 1.35)


def _candidate_score(
    source_station_row: pd.Series,
    target_row: pd.Series,
    same_zone: bool,
    target_state=None,
    source_zone_type: Optional[str] = None,
    target_zone_type: Optional[str] = None,
) -> float:
    """
    Higher score means the target station is a better overflow sink.
    """
    chargers = int(target_row.get("chargers", 1))
    power_per_charger_kw = int(target_row.get("power_per_charger_kw", 7))
    capacity_kw = max(1, chargers * power_per_charger_kw)

    target_type = str(target_row.get("station_type", "standard"))
    util_base = float(target_row.get("utilization_base", 0.35))

    # Bigger stations can absorb more.
    capacity_factor = 0.90 + min(0.60, capacity_kw / 130.0)

    # Lower baseline utilization => more attractive.
    idle_factor = 1.18 - (util_base * 0.58)

    # Station type matters.
    type_factor = _station_type_factor(target_type)

    # Same-zone stations should get first preference.
    zone_factor = 1.75 if same_zone else 0.92

    # Live/estimated availability.
    availability_factor = _availability_factor(
        target_row=target_row,
        target_state=target_state,
        source_zone_type=source_zone_type,
        target_zone_type=target_zone_type,
    )

    # Slight bonus if target zone type matches source zone type.
    type_match_bonus = 1.05 if source_zone_type and target_zone_type and source_zone_type == target_zone_type else 1.0

    score = zone_factor * capacity_factor * idle_factor * type_factor * availability_factor * type_match_bonus
    return max(0.05, score)


def predict_spillover(
    station_row: pd.Series,
    stations_df: pd.DataFrame,
    demand_kw: float,
    station_state_map: Optional[dict[str, dict]] = None,
    zones_df: Optional[pd.DataFrame] = None,
    scenario: str = "normal",
) -> list[dict]:
    """
    Predict where overflow charging demand should go when a station is full / near-full.

    Works with your current routes.py as-is.
    If you later pass station_state_map and zones_df, it becomes even better.
    """
    if stations_df.empty:
        return []

    source_station_id = station_row["station_id"]
    source_zone_id = station_row["zone_id"]
    source_chargers = int(station_row.get("chargers", 1))
    source_power = int(station_row.get("power_per_charger_kw", 7))
    source_capacity_kw = max(1, source_chargers * source_power)

    # Pressure of load on the source station.
    source_pressure = demand_kw / source_capacity_kw

    # How much of the demand should spill to other stations.
    spill_ratio = _spillover_ratio(source_pressure, scenario=scenario)
    spillover_total_kw = round(demand_kw * spill_ratio, 2)

    if spillover_total_kw <= 0:
        return []

    # Optional zone type lookup.
    zone_type_lookup = {}
    if zones_df is not None and not zones_df.empty:
        if "zone_id" in zones_df.columns and "zone_type" in zones_df.columns:
            zone_type_lookup = zones_df.set_index("zone_id")["zone_type"].to_dict()

    source_zone_type = zone_type_lookup.get(source_zone_id)

    # Candidate stations: everything except the source station itself.
    candidates = stations_df[stations_df["station_id"] != source_station_id].copy()
    if candidates.empty:
        return []

    scored_candidates = []
    for _, target_row in candidates.iterrows():
        target_station_id = target_row["station_id"]
        target_zone_id = target_row["zone_id"]
        same_zone = target_zone_id == source_zone_id

        target_zone_type = zone_type_lookup.get(target_zone_id)
        target_state = None
        if station_state_map is not None:
            target_state = station_state_map.get(target_station_id)

        score = _candidate_score(
            source_station_row=station_row,
            target_row=target_row,
            same_zone=same_zone,
            target_state=target_state,
            source_zone_type=source_zone_type,
            target_zone_type=target_zone_type,
        )

        if target_state is not None:
            target_status = str(_get_state_value(target_state, "status", "unknown")).lower()
            target_queue = float(_get_state_value(target_state, "queue_risk", 0.25))
        else:
            target_status = "unknown"
            target_queue = 0.25

        scored_candidates.append({
            "station_id": target_station_id,
            "zone_id": target_zone_id,
            "same_zone": same_zone,
            "score": score,
            "status": target_status,
            "queue_risk": target_queue,
        })

    if not scored_candidates:
        return []

    # Keep only the best few targets so the output stays readable.
    scored_candidates = sorted(
        scored_candidates,
        key=lambda x: (-x["score"], x["station_id"])
    )[:5]

    total_score = sum(c["score"] for c in scored_candidates)
    if total_score <= 0:
        # fallback to equal split
        total_score = len(scored_candidates)
        for c in scored_candidates:
            c["score"] = 1.0

    raw_allocations = [
        spillover_total_kw * (c["score"] / total_score) for c in scored_candidates
    ]
    rounded_allocations = [round(v, 2) for v in raw_allocations]

    # Fix rounding drift so totals stay close to spillover_total_kw.
    drift = round(spillover_total_kw - sum(rounded_allocations), 2)
    if rounded_allocations:
        rounded_allocations[-1] = round(rounded_allocations[-1] + drift, 2)

    spillovers = []
    for rank, (candidate, allocated_kw) in enumerate(zip(scored_candidates, rounded_allocations), start=1):
        if allocated_kw <= 0:
            continue

        if candidate["same_zone"]:
            reason = "same_zone_capacity_available"
        elif candidate["status"] in {"free", "engaged"}:
            reason = "nearby_capacity_available"
        elif candidate["status"] == "near_full":
            reason = "limited_capacity_nearby"
        else:
            reason = "estimated_capacity_available"

        confidence = _clamp(0.58 + (candidate["score"] / total_score) * 0.32, 0.58, 0.96)

        spillovers.append({
            "from_station": source_station_id,
            "to_station": candidate["station_id"],
            "to_zone": candidate["zone_id"],
            "spillover_kw": round(allocated_kw, 2),
            "same_zone": candidate["same_zone"],
            "target_status": candidate["status"],
            "absorption_score": round(candidate["score"], 3),
            "priority_rank": rank,
            "confidence": round(confidence, 2),
            "reason": reason,
        })

    return spillovers