# ChargeRadar — Occupancy-Aware EV Charging Traffic Control for BESCOM

ChargeRadar is a BESCOM-facing AI decision-support system that forecasts where EV charging demand will rise, predicts which charging stations will be engaged or full, estimates time-to-full / time-to-free, identifies spillover demand to nearby stations, and recommends grid-aware actions for charging management and infrastructure planning.

## What this prototype does

ChargeRadar is built as a **two-role dashboard**:

* **Govt / BESCOM view** — a planning and operations console for monitoring zone-level EV charging stress, station congestion, spillover, and infrastructure needs.
* **Normal user view** — a simplified charging assistant that shows nearby charging status and gives clear advice like charge now, wait, or try later.

The system is designed to be **actionable, explainable, and deployment-friendly** as a decision-support layer. It does **not** modify the existing distribution system.

## Core capabilities

### 1. Demand forecasting

* Predicts EV charging demand by **zone**, **date/day index**, and **hour**.
* Captures residential evening spikes, commercial daytime peaks, corridor bursts, weekend effects, and growth trends.
* Produces CSV-backed synthetic demand history for repeatable demos and analysis.

### 2. Station occupancy intelligence

* Estimates whether a station is **free**, **engaged**, **near_full**, or **full**.
* Computes:

  * **occupancy**
  * **queue risk**
  * **estimated wait time**
  * **time to full**
  * **time to free**
  * **occupancy trend**

### 3. Spillover prediction

* When stations get congested, ChargeRadar predicts where charging demand will move next.
* Prioritizes nearby stations and same-zone alternatives.
* Returns ranked spillover flows with confidence and absorption score.

### 4. Grid-aware decisions

* Produces operational actions such as:

  * **DEFER** — shift charging to off-peak hours
  * **ABSORB** — a zone can safely take more charging
  * **MONITOR** — watch the zone for the next peak
  * **BUILD** — prioritize new charging infrastructure

### 5. Explainable outputs

* Every zone includes a natural-language explanation.
* Decision outputs are backed by visible metrics and thresholds.
* Designed for planner/operator trust and demo clarity.

## System design

ChargeRadar uses a modular backend architecture:

* **`synthetic_data.py`** — generates realistic zones, stations, and demand time series.
* **`forecasting.py`** — predicts demand using zone type, hour, day, growth, and scenario logic.
* **`occupancy.py`** — estimates station state and congestion.
* **`spillover.py`** — computes overflow demand routing to nearby stations.
* **`decisions.py`** — converts demand and congestion signals into operational actions.
* **`routes.py`** — orchestrates the full simulation and exposes the API.
* **`app_frontend.py`** — Streamlit dashboard for Govt and user views.

## Tech stack

* **Backend:** FastAPI
* **Frontend:** Streamlit
* **Data processing:** Pandas, NumPy
* **Simulation layer:** deterministic synthetic data + rule-based forecasting
* **Visualization:** Streamlit cards, metrics, charts, and drill-down views

## How it works

1. Synthetic zone and station data are created.
2. Hourly demand is generated for each zone.
3. The backend computes:

   * zone demand
   * station occupancy
   * queue risk
   * spillover flows
   * grid-aware actions
4. The frontend visualizes the result for either:

   * BESCOM / Govt users
   * normal users

## Data model

### Zones

Each zone includes:

* zone ID
* zone type
* grid capacity
* EV density
* station density
* growth rate
* feeder ID
* priority band

### Stations

Each station includes:

* station ID
* zone ID
* station type
* charger count
* charger power
* utilization base

### Demand history

The demand CSV includes:

* day
* hour
* zone ID
* zone type
* baseline demand
* actual demand
* grid capacity
* load ratio
* stress level
* weekend flag

## API endpoint

### `GET /simulate`

Returns a full city snapshot.

Query parameters:

* `day` — synthetic day index
* `hour` — hour of day
* `scenario` — internal demand scenario

Example:

```bash
/simulate?day=0&hour=19
```

## Frontend views

### Govt / BESCOM

Shows:

* city overview
* hotspot alerts
* heatmap-style zone cards
* zone drill-down
* station drill-down
* spillover details
* demand graph
* infrastructure recommendation

### Normal user

Shows:

* selected zone
* charging status
* station availability
* wait time
* simple advice: charge now, wait, or charge later

## Setup

### 1) Install dependencies

```bash
pip install fastapi uvicorn pandas numpy streamlit
```

### 2) Generate the CSV data

```bash
python generate_data.py
```

### 3) Run the backend

```bash
uvicorn app.main:app --reload
```

### 4) Run the frontend

```bash
streamlit run app_frontend.py
```

## Notes

* The system is intentionally deterministic for stable demos.
* The data layer is synthetic but structured to resemble a real operational workflow.
* The design keeps sensitive grid operations as decision support only.

## Future improvements

* Replace synthetic data with real BESCOM datasets.
* Add geospatial station mapping.
* Introduce feeder-level constraints and optimization.
* Train a data-driven forecasting model on historical time series.
* Add a richer recommendation engine for infrastructure prioritization.

## License

This prototype is for hackathon demonstration and evaluation purposes.