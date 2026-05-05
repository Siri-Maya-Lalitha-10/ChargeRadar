from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter

from app.core.decisions import get_zone_decision
from app.core.explain import explain_decision
from app.core.forecasting import forecast_zone_demand
from app.core.occupancy import compute_station_state
from app.core.spillover import predict_spillover
from app.core.synthetic_data import (
    generate_demand_timeseries,
    generate_stations,
    generate_zones,
)

router = APIRouter()

DATA_DIR = Path("data")


def _load_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    zones_path = DATA_DIR / "zones.csv"
    stations_path = DATA_DIR / "stations.csv"
    demand_path = DATA_DIR / "demand_timeseries.csv"

    if zones_path.exists():
        zones_df = pd.read_csv(zones_path)
    else:
        zones_df = generate_zones()

    if stations_path.exists():
        stations_df = pd.read_csv(stations_path)
    else:
        stations_df = generate_stations()

    if demand_path.exists():
        demand_df = pd.read_csv(demand_path)
    else:
        demand_df = generate_demand_timeseries(zones_df, days=14, scenario="normal", seed=42)

    return zones_df, stations_df, demand_df


zones_df, stations_df, demand_df = _load_tables()


def _stable_occupancy(zone_id: str, station_id: str, day: int, hour: int) -> float:
    """
    Deterministic occupancy so the demo stays stable on refresh.
    """
    raw = f"{zone_id}|{station_id}|{day}|{hour}".encode("utf-8")
    digest = hashlib.md5(raw).hexdigest()
    value = int(digest[:8], 16)

    # 0.28 to 0.74 range
    return round(0.28 + ((value % 47) / 100), 2)


def _demand_trend(zone_type: str, hour: int) -> float:
    """
    Simple short-term trend signal used by the decision layer.
    """
    zone_type = (zone_type or "").lower()

    if zone_type == "residential":
        if 18 <= hour <= 22:
            return 0.70
        if 6 <= hour <= 9:
            return 0.30
        return 0.10

    if zone_type == "commercial":
        if 10 <= hour <= 16:
            return 0.55
        if 7 <= hour <= 9:
            return 0.25
        return 0.12

    if zone_type == "corridor":
        if 7 <= hour <= 10 or 17 <= hour <= 21:
            return 0.60
        return 0.10

    # mixed
    if 16 <= hour <= 21:
        return 0.40
    return 0.15


def _zone_status(load_ratio: float) -> str:
    if load_ratio >= 0.75:
        return "HIGH_LOAD"
    if load_ratio >= 0.55:
        return "MEDIUM_LOAD"
    return "LOW_LOAD"


def _scenario_multiplier(zone_type: str, hour: int, scenario: str) -> float:
    """
    Keep scenarios visible in the demo even when using CSV-based demand.
    """
    scenario = (scenario or "normal").lower()

    if scenario == "residential_peak" and zone_type == "residential" and 18 <= hour <= 22:
        return 1.85
    if scenario == "commercial_peak" and zone_type == "commercial" and 10 <= hour <= 16:
        return 1.65
    if scenario == "corridor_burst" and zone_type == "corridor" and (7 <= hour <= 10 or 17 <= hour <= 21):
        return 1.80
    if scenario == "underutilized_night" and (hour >= 23 or hour <= 5):
        return 1.25
    if scenario == "event_spike" and hour in (18, 19, 20):
        return 1.45

    return 1.0


def _extract_demand_value(filtered: pd.DataFrame) -> float:
    """
    Works with either:
    - actual_demand_kw
    - predicted_demand_kw
    - demand_kw
    - baseline_demand_kw
    """
    if filtered.empty:
        return 0.0

    row = filtered.iloc[0]
    for col in ("actual_demand_kw", "predicted_demand_kw", "demand_kw", "baseline_demand_kw"):
        if col in filtered.columns:
            return float(row[col])

    # fallback if column names change later
    numeric_cols = [c for c in filtered.columns if pd.api.types.is_numeric_dtype(filtered[c])]
    if numeric_cols:
        return float(row[numeric_cols[0]])

    return 0.0


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/simulate")
def simulate(day: int = 0, hour: int = 18, scenario: str = "normal"):
    """
    Simulate one city-wide EV charging snapshot.

    Returns:
    - zone demand
    - station engagement
    - queue risk
    - time-to-full / time-to-free
    - spillover
    - action labels
    - infrastructure guidance
    """
    results: list[dict[str, Any]] = []
    station_state_map: dict[str, dict[str, Any]] = {}
    zone_temp: list[dict[str, Any]] = []

    # Pass 1: forecast demand and compute station states
    for _, zone in zones_df.iterrows():
        filtered = pd.DataFrame()
        if demand_df is not None and not demand_df.empty:
            zone_col = "zone_id" if "zone_id" in demand_df.columns else None
            hour_col = "hour" if "hour" in demand_df.columns else None
            day_col = "day" if "day" in demand_df.columns else None
            if zone_col and hour_col and day_col:
                filtered = demand_df[
                    (demand_df[zone_col] == zone["zone_id"]) &
                    (demand_df[hour_col] == hour) &
                    (demand_df[day_col] == day)
                ]

        if not filtered.empty:
            demand = _extract_demand_value(filtered)
            demand *= _scenario_multiplier(str(zone["zone_type"]), hour, scenario)
        else:
            demand = forecast_zone_demand(zone, hour, day, scenario=scenario)

        zone_stations = stations_df[stations_df["zone_id"] == zone["zone_id"]]
        demand_per_station = demand / max(len(zone_stations), 1)

        station_outputs = []
        for _, station in zone_stations.iterrows():
            current_occupancy = _stable_occupancy(
                zone_id=str(zone["zone_id"]),
                station_id=str(station["station_id"]),
                day=day,
                hour=hour,
            )

            state = compute_station_state(
                chargers=int(station["chargers"]),
                power_per_charger_kw=int(station["power_per_charger_kw"]),
                incoming_demand_kw=demand_per_station,
                current_occupancy=current_occupancy,
                station_type=str(station.get("station_type", "standard")),
                utilization_base=float(station.get("utilization_base", 0.35)),
                scenario=scenario,
            )

            station_state_map[str(station["station_id"])] = {
                "occupancy": state.occupancy,
                "status": state.status,
                "queue_risk": state.queue_risk,
                "occupancy_trend": state.occupancy_trend,
                "time_to_full_minutes": state.time_to_full_minutes,
                "time_to_free_minutes": state.time_to_free_minutes,
                "estimated_wait_minutes": state.estimated_wait_minutes,
                "zone_id": str(zone["zone_id"]),
            }

            station_outputs.append({
                "station_id": station["station_id"],
                "status": state.status,
                "occupancy": state.occupancy,
                "queue_risk": state.queue_risk,
                "occupancy_trend": state.occupancy_trend,
                "estimated_wait_minutes": state.estimated_wait_minutes,
                "time_to_full_minutes": state.time_to_full_minutes,
                "time_to_free_minutes": state.time_to_free_minutes,
                "spillover": [],
            })

        zone_temp.append({
            "zone": zone,
            "demand": demand,
            "stations": station_outputs,
            "zone_stations": zone_stations,
            "demand_per_station": demand_per_station,
        })

    # Pass 2: spillover + decisions + explanations
    for item in zone_temp:
        zone = item["zone"]
        demand = float(item["demand"])
        station_outputs = item["stations"]
        zone_stations = item["zone_stations"]
        demand_per_station = float(item["demand_per_station"])

        total_spillover_kw = 0.0
        spillover_count = 0
        queue_risks = []

        # Compute spillover for congested stations
        for idx, (_, station) in enumerate(zone_stations.iterrows()):
            station_id = str(station["station_id"])
            state = station_state_map.get(station_id, {})

            queue_risks.append(float(state.get("queue_risk", 0.0)))

            if state.get("status") in {"full", "near_full"}:
                spillovers = predict_spillover(
                    station_row=station,
                    stations_df=stations_df,
                    demand_kw=demand_per_station,
                    station_state_map=station_state_map,
                    zones_df=zones_df,
                    scenario=scenario,
                )
                station_outputs[idx]["spillover"] = spillovers
                spillover_count += len(spillovers)
                total_spillover_kw += sum(float(s.get("spillover_kw", 0.0)) for s in spillovers)

        load_ratio = demand / max(float(zone["grid_capacity_kw"]), 1.0)
        growth_score = min(1.0, float(zone.get("growth_rate", 0.04)) * 12.0)
        station_pressure = max(queue_risks) if queue_risks else 0.0
        spillover_risk = min(1.0, total_spillover_kw / max(demand, 1.0))
        demand_trend = _demand_trend(str(zone["zone_type"]), hour)
        station_density = float(zone.get("station_density", 3))

        decision = get_zone_decision(
            demand_kw=demand,
            grid_capacity_kw=float(zone["grid_capacity_kw"]),
            growth_score=growth_score,
            station_pressure=station_pressure,
            spillover_risk=spillover_risk,
            demand_trend=demand_trend,
            station_density=station_density,
            scenario=scenario,
        )

        zone_status = _zone_status(decision.load_ratio)

        explanation = explain_decision(
            zone_id=str(zone["zone_id"]),
            action=decision.action,
            demand_kw=demand,
            grid_kw=float(zone["grid_capacity_kw"]),
            occupancy=station_outputs[0]["status"] if station_outputs else "unknown",
            load_ratio=decision.load_ratio,
            risk_level=decision.risk_level,
            suggested_window=decision.suggested_charging_window,
            infrastructure_recommendation=decision.infrastructure_recommendation,
            station_pressure=station_pressure,
            spillover_risk=spillover_risk,
            growth_score=growth_score,
            queue_risk=station_pressure,
        )

        results.append({
            "zone": {
                "id": zone["zone_id"],
                "type": zone["zone_type"],
                "demand": round(demand, 2),
                "capacity": float(zone["grid_capacity_kw"]),
                "load_ratio": round(load_ratio, 2),
                "status": zone_status,
                "risk_level": decision.risk_level,
                "score": decision.score,
                "recommended_action": decision.action,
                "suggested_window": decision.suggested_charging_window,
                "infrastructure_recommendation": decision.infrastructure_recommendation,
                "growth_score": round(growth_score, 2),
                "station_pressure": round(station_pressure, 2),
                "spillover_risk": round(spillover_risk, 2),
            },
            "stations": station_outputs,
            "spillover_count": spillover_count,
            "spillover_kw": round(total_spillover_kw, 2),
            "explanation": explanation,
        })

    overview = {
        "zones": len(results),
        "high_load_zones": sum(1 for r in results if r["zone"]["status"] == "HIGH_LOAD"),
        "defer_zones": sum(1 for r in results if r["zone"]["recommended_action"] == "DEFER"),
        "build_zones": sum(1 for r in results if r["zone"]["recommended_action"] == "BUILD"),
        "full_stations": sum(
            1
            for r in results
            for s in r["stations"]
            if s["status"] == "full"
        ),
        "spillover_flows": sum(r["spillover_count"] for r in results),
        "total_predicted_demand_kw": round(sum(r["zone"]["demand"] for r in results), 2),
    }

    return {
        "day": day,
        "hour": hour,
        "scenario": scenario,
        "overview": overview,
        "results": results,
    }