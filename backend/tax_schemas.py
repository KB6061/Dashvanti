from decimal import Decimal
from pydantic import BaseModel, Field

class TaxLineItem(BaseModel):
    id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=100)

class OrderTaxCalculation(BaseModel):
    customer_zip: str = Field(pattern=r'^\d{5}(?:-\d{4})?$')
    items: list[TaxLineItem] = Field(min_length=1, max_length=100)
    delivery_fee: Decimal = Field(ge=0, le=10000, decimal_places=2)
    platform_fee: Decimal = Field(ge=0, le=10000, decimal_places=2)
