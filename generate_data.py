from app.core.synthetic_data import generate_zones, generate_stations, generate_demand_timeseries

zones = generate_zones()
stations = generate_stations()
demand = generate_demand_timeseries(zones)

zones.to_csv("data/zones.csv", index=False)
stations.to_csv("data/stations.csv", index=False)
demand.to_csv("data/demand_timeseries.csv", index=False)

print("✅ CSV files created!")