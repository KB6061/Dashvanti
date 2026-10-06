from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field


class PayoutSettingsInput(BaseModel):
    manual_enabled: bool = True
    automated_enabled: bool = False
    environment: Literal['test', 'live'] = 'test'
    secret_key: str = Field(default='', max_length=300)
    confirm_live: bool = False


class PayoutRecipientInput(BaseModel):
    user_id: int = Field(gt=0)
    account_id: str = Field(pattern=r'^acct_[A-Za-z0-9]+$', max_length=100)


class PayoutInput(BaseModel):
    order_id: int = Field(gt=0)
    payee_role: Literal['driver', 'restaurant']
    mode: Literal['manual', 'stripe'] = 'manual'
    confirmation: str = Field(default='', max_length=120)
    expected_amount: Decimal = Field(gt=0, decimal_places=2)
