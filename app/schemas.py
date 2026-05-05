from pydantic import BaseModel


class ScenarioRequest(BaseModel):
    day: int
    hour: int


class ForecastResponse(BaseModel):
    zone_id: str
    hour: int
    predicted_demand_kw: float
    grid_capacity_kw: float
    action: str
    explanation: str