from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class TicketInput(Input):
    order_id: int | None = Field(None, gt=0)
    category: str = Field(min_length=1, max_length=120)
    subcategory: str = Field('', max_length=120)
    priority: Literal['Low', 'Medium', 'High', 'Critical', 'Emergency'] = 'Medium'
    description: str = Field(min_length=1, max_length=10000)


class TicketAction(Input):
    action: Literal['reply', 'note', 'assign', 'escalate', 'status', 'merge']
    body: str = Field('', max_length=10000)
    assignee_id: int | None = Field(None, gt=0)
    department: str = Field('Support', max_length=80)
    priority: Literal['Low', 'Medium', 'High', 'Critical', 'Emergency'] | None = None
    status: Literal['Open', 'Assigned', 'In Progress', 'Waiting Customer', 'Escalated', 'Resolved', 'Closed'] | None = None
    merge_into: int | None = Field(None, gt=0)


class FavoriteInput(Input):
    kind: Literal['restaurant', 'menu']
    target_id: int = Field(gt=0)
    enabled: bool


class WalletInput(Input):
    amount: Decimal = Field(gt=0, le=1000, decimal_places=2)
    gateway: str = Field(max_length=30)
    request_key: str = Field(min_length=16, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')


class WalletTransfer(Input):
    recipient_email: str = Field(min_length=3, max_length=254)
    amount: Decimal = Field(gt=0, le=1000, decimal_places=2)
    request_key: str = Field(min_length=16, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')
    current_password: str = Field(min_length=1, max_length=128)


class GatewayInput(Input):
    name: str = Field(min_length=1, max_length=30)
    enabled: bool
    countries: list[Literal['US', 'IN']] = Field(default_factory=lambda: ['US', 'IN'])
    reason: str = Field(min_length=3, max_length=500)


class ReviewInput(Input):
    order_id: int = Field(gt=0)
    rating: int = Field(ge=1, le=5)
    title: str = Field('', max_length=120)
    comment: str = Field(min_length=1, max_length=2000)


class ReviewAction(Input):
    action: Literal['helpful', 'report', 'approve', 'reject']
    reason: str = Field('', max_length=500)


class LocationInput(Input):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    language: str = Field('en', max_length=20)
    timezone: str = Field('UTC', max_length=80)


class RollbackInput(Input):
    reason: str = Field(min_length=3, max_length=500)


class VerificationInput(Input):
    user_id: int = Field(gt=0)
    verified: bool
    reason: str = Field(min_length=3, max_length=500)


class RegionInput(Input):
    id: int = Field(gt=0)
    country: Literal['US','IN']
    city: str = Field('',max_length=100)
    state: str = Field('',max_length=100)
    reason: str = Field(min_length=3,max_length=500)


class WalletRefundInput(Input):
    refund_id: str = Field(min_length=8, max_length=120, pattern=r'^refund:[A-Za-z0-9:_-]+$')
    reason: str = Field(min_length=3, max_length=500)


class AdminLoginInput(Input):
    email: str = Field('',max_length=254)
    password: str = Field(min_length=1,max_length=128)
    role: Literal['admin']='admin'


class SLAInput(Input):
    priority: Literal['Low','Medium','High','Critical','Emergency']
    minutes: int = Field(ge=1,le=10080)
    reason: str = Field(min_length=3,max_length=500)
