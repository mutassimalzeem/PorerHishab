from decimal import Decimal
from pydantic import BaseModel

class CategoryForecast(BaseModel):
    category: str
    forecast: Decimal
    observations: int


class BudgetForecast(BaseModel):
    months_ahead: int
    forecast: Decimal
    historical_average: Decimal
    recent_average: Decimal
    confidence: str
    months_observed: int
    categories: list[CategoryForecast]