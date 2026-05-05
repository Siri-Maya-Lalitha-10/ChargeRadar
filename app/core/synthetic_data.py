from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd


DATA_DIR = Path("data")


# ----------------------------
# Helpers
# ----------------------------
def _rng(seed: int | None = None) -> np.random.Generator:
    return np.random.default_rng(seed)


def _is_weekend(day: int) -> bool:
    # simple synthetic calendar: day 5 and 6 behave like weekend, repeating
    return (day % 7) in (5, 6)


def _scenario_multiplier(zone_type: str, hour: int, scenario: str) -> float:
    """
    Scenario controls let us simulate different city behaviors for demo/testing.
    Kept strong enough to visibly create peak behavior.
    """
    scenario = (scenario or "normal").lower()
    zone_type = (zone_type or "").lower()

    if scenario == "residential_peak" and zone_type == "residential" and 18 <= hour <= 22:
        return 1.35
    if scenario == "commercial_peak" and zone_type == "commercial" and 10 <= hour <= 16:
        return 1.25
    if scenario == "corridor_burst" and zone_type == "corridor" and (7 <= hour <= 10 or 17 <= hour <= 21):
        return 1.30
    if scenario == "off_peak_incentive" and hour >= 22:
        return 1.20
    if scenario == "event_spike" and hour in (18, 19, 20):
        return 1.45

    return 1.0


# ----------------------------
# Core entities
# ----------------------------
def generate_zones() -> pd.DataFrame:
    """
    Zone table tuned to create at least one clearly stressed zone during peak hours.
    """
    return pd.DataFrame([
        {
            "zone_id": "Z1",
            "zone_type": "residential",
            "grid_capacity_kw": 380,
            "ev_density": 170,
            "station_density": 2,
            "growth_rate": 0.080,
            "feeder_id": "F1",
            "priority_band": "high",
        },
        {
            "zone_id": "Z2",
            "zone_type": "commercial",
            "grid_capacity_kw": 600,
            "ev_density": 120,
            "station_density": 4,
            "growth_rate": 0.055,
            "feeder_id": "F2",
            "priority_band": "medium",
        },
        {
            "zone_id": "Z3",
            "zone_type": "corridor",
            "grid_capacity_kw": 460,
            "ev_density": 110,
            "station_density": 2,
            "growth_rate": 0.070,
            "feeder_id": "F3",
            "priority_band": "high",
        },
        {
            "zone_id": "Z4",
            "zone_type": "mixed",
            "grid_capacity_kw": 520,
            "ev_density": 135,
            "station_density": 3,
            "growth_rate": 0.060,
            "feeder_id": "F4",
            "priority_band": "high",
        },
    ])


def generate_stations() -> pd.DataFrame:
    """
    Station table tuned so congestion is visible during peak demand.
    """
    return pd.DataFrame([
        {
            "station_id": "S1",
            "zone_id": "Z1",
            "station_type": "slow",
            "chargers": 5,
            "power_per_charger_kw": 7,
            "utilization_base": 0.60,
        },
        {
            "station_id": "S2",
            "zone_id": "Z1",
            "station_type": "slow",
            "chargers": 4,
            "power_per_charger_kw": 7,
            "utilization_base": 0.58,
        },
        {
            "station_id": "S3",
            "zone_id": "Z2",
            "station_type": "standard",
            "chargers": 10,
            "power_per_charger_kw": 7,
            "utilization_base": 0.46,
        },
        {
            "station_id": "S4",
            "zone_id": "Z3",
            "station_type": "fast",
            "chargers": 4,
            "power_per_charger_kw": 15,
            "utilization_base": 0.62,
        },
        {
            "station_id": "S5",
            "zone_id": "Z4",
            "station_type": "standard",
            "chargers": 6,
            "power_per_charger_kw": 7,
            "utilization_base": 0.52,
        },
    ])


# ----------------------------
# Demand synthesis
# ----------------------------
def demand_pattern(
    zone_type: str,
    hour: int,
    day: int = 0,
    ev_density: float = 100,
    growth_rate: float = 0.04,
    scenario: str = "normal",
    grid_capacity_kw: float = 500,
    seed: int | None = None,
) -> float:
    """
    Synthetic EV charging demand in kW.

    Uses:
    - zone type
    - hour of day
    - weekend/day trend
    - EV density
    - growth trend
    - optional scenario spikes
    - grid capacity anchor so high-load cases can appear
    """
    from app.core.forecasting import forecast_zone_demand

    row = pd.Series(
        {
            "zone_id": "synthetic",
            "zone_type": zone_type,
            "grid_capacity_kw": grid_capacity_kw,
            "ev_density": ev_density,
            "station_density": 3,
            "growth_rate": growth_rate,
        }
    )

    # Deterministic forecast-based demand for consistency and stronger peaks
    demand = forecast_zone_demand(
        zone_row=row,
        hour=hour,
        day=day,
        scenario=scenario,
    )

    # Tiny stable variation for realism
    rng = _rng(seed)
    demand = demand + float(rng.normal(0, max(2.0, demand * 0.03)))

    return max(0.0, round(float(demand), 2))


def generate_demand_timeseries(
    zones: pd.DataFrame,
    days: int = 14,
    scenario: str = "normal",
    seed: int | None = 42,
) -> pd.DataFrame:
    """
    Creates a realistic hourly demand table for all zones.
    Useful for CSV export, plotting, or future ML training.
    """
    rng = _rng(seed)
    rows = []

    for day in range(days):
        for hour in range(24):
            for _, z in zones.iterrows():
                baseline = demand_pattern(
                    zone_type=z["zone_type"],
                    hour=hour,
                    day=day,
                    ev_density=float(z["ev_density"]),
                    growth_rate=float(z["growth_rate"]),
                    scenario="normal",
                    grid_capacity_kw=float(z["grid_capacity_kw"]),
                    seed=int(rng.integers(0, 1_000_000)),
                )

                actual = demand_pattern(
                    zone_type=z["zone_type"],
                    hour=hour,
                    day=day,
                    ev_density=float(z["ev_density"]),
                    growth_rate=float(z["growth_rate"]),
                    scenario=scenario,
                    grid_capacity_kw=float(z["grid_capacity_kw"]),
                    seed=int(rng.integers(0, 1_000_000)),
                )

                # Add one more strong but controlled scenario boost at CSV generation time
                actual *= _scenario_multiplier(z["zone_type"], hour, scenario)

                grid_capacity = float(z["grid_capacity_kw"])
                load_ratio = actual / grid_capacity if grid_capacity > 0 else 0.0

                if load_ratio >= 1.0:
                    stress_level = "critical"
                elif load_ratio >= 0.8:
                    stress_level = "high"
                elif load_ratio >= 0.5:
                    stress_level = "medium"
                else:
                    stress_level = "low"

                rows.append({
                    "day": day,
                    "hour": hour,
                    "zone_id": z["zone_id"],
                    "zone_type": z["zone_type"],
                    "baseline_demand_kw": round(baseline, 2),
                    "actual_demand_kw": round(actual, 2),
                    "grid_capacity_kw": grid_capacity,
                    "load_ratio": round(load_ratio, 3),
                    "stress_level": stress_level,
                    "is_weekend": _is_weekend(day),
                })

    return pd.DataFrame(rows)


# ----------------------------
# CSV export
# ----------------------------
def save_data(
    zones: pd.DataFrame,
    stations: pd.DataFrame,
    demand: pd.DataFrame,
    data_dir: Path = DATA_DIR,
) -> None:
    """
    Export synthetic data to CSV so the project has a visible data pipeline.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    zones.to_csv(data_dir / "zones.csv", index=False)
    stations.to_csv(data_dir / "stations.csv", index=False)
    demand.to_csv(data_dir / "demand_timeseries.csv", index=False)


def build_all_data(days: int = 14, scenario: str = "normal", seed: int = 42) -> dict[str, pd.DataFrame]:
    """
    Convenience helper for generating and exporting all datasets.
    """
    zones = generate_zones()
    stations = generate_stations()
    demand = generate_demand_timeseries(zones, days=days, scenario=scenario, seed=seed)
    save_data(zones, stations, demand)
    return {
        "zones": zones,
        "stations": stations,
        "demand": demand,
    }


if __name__ == "__main__":
    data = build_all_data(days=14, scenario="residential_peak", seed=42)
    print(data["zones"].head())
    print(data["stations"].head())
    print(data["demand"].head())