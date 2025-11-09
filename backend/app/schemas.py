from pydantic import BaseModel
from typing import Optional


class HoldingCreate(BaseModel):
    symbol: str
    quantity: float
    currency: Optional[str] = "USD"
    brokerage_firm: Optional[str] = None
    account_number: Optional[str] = None
    account_type: Optional[str] = None
    security_name: Optional[str] = None
    price_per_unit: Optional[float] = None
    market_value: Optional[float] = None
    cost_basis: Optional[float] = None
    gain_loss: Optional[float] = None
    gain_loss_percent: Optional[float] = None


class HoldingRead(BaseModel):
    id: int
    symbol: str
    quantity: float
    currency: str
    brokerage_firm: Optional[str] = None
    account_number: Optional[str] = None
    account_type: Optional[str] = None
    security_name: Optional[str] = None
    price_per_unit: Optional[float] = None
    market_value: Optional[float] = None
    cost_basis: Optional[float] = None
    gain_loss: Optional[float] = None
    gain_loss_percent: Optional[float] = None

    class Config:
        from_attributes = True


class FinancialItemCreate(BaseModel):
    name: str
    value: float
    period: Optional[str] = "latest"


class FinancialItemRead(BaseModel):
    id: int
    name: str
    value: float
    period: str

    class Config:
        from_attributes = True
