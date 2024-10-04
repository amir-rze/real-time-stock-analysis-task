from pydantic import BaseModel
from datetime import datetime
# Define the Pydantic model for the Data validation
class SummaryOut(BaseModel):
    stock_symbol: str
    sell_count: int
    buy_count: int

# Define the Pydantic model for the Data response validation
class DataOut(BaseModel):
    stock_symbol: str
    opening_price: float
    closing_price: float
    high: float
    low: float
    volume: int
    timestamp: datetime

