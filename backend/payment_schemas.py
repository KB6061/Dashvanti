from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from backend.schemas import Checkout


class StrictInput(BaseModel):
    model_config = ConfigDict(extra='forbid')


class PayInput(StrictInput):
    checkout: Checkout
    instrument: Literal['UPI', 'UPI_INTENT', 'REDIRECT'] = 'UPI'


class StatusInput(StrictInput):
    transaction_id: int = Field(gt=0)


class RefundInput(StrictInput):
    amount: int = Field(ge=100)
    reason: str = Field(min_length=3, max_length=250)
    request_key: str = Field(min_length=16, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')


class RefundWithPayment(RefundInput):
    transaction_id: int = Field(gt=0)


class SettingsInput(StrictInput):
    environment: Literal['sandbox', 'production'] = 'sandbox'
    api_version: Literal['v1', 'v2'] = 'v2'
    merchant_id: str | None = Field(None, max_length=120)
    salt_key: str | None = Field(None, max_length=500)
    salt_index: int = Field(1, ge=1, le=100)
    api_key: str | None = Field(None, max_length=500)
    client_id: str | None = Field(None, max_length=120)
    client_secret: str | None = Field(None, max_length=500)
    client_version: int = Field(1, ge=1, le=100)
    webhook_username: str | None = Field(None, max_length=120)
    webhook_password: str | None = Field(None, max_length=500)
    confirm_production: bool = False


class ToggleInput(StrictInput):
    method: Literal['phonepe', 'razorpay', 'cashfree']
    enabled: bool


class CountryInput(StrictInput):
    country: str = Field(max_length=60)


class RestaurantCurrencyInput(StrictInput):
    restaurant_id: int = Field(gt=0)
    currency: Literal['USD', 'INR']
    confirm_prices: bool


class SettlementInput(StrictInput):
    reference: str = Field(min_length=3, max_length=120)
    environment: Literal['sandbox', 'production']
    amount: int = Field(ge=0)
    currency: Literal['INR'] = 'INR'
    status: Literal['PENDING', 'SETTLED', 'FAILED']
    settled_at: datetime | None = None
