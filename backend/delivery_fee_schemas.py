from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, model_validator

Money = lambda default=...: Field(default=default, ge=0, le=999999, max_digits=12, decimal_places=2, allow_inf_nan=False)


class FeeInput(BaseModel):
    model_config = {'validate_default': True}


class CountryInput(FeeInput):
    country_code: str = Field(pattern=r'^[A-Z]{2}$')
    country_name: str = Field(min_length=1, max_length=100)
    currency_code: str = Field(pattern=r'^[A-Z]{3}$')
    currency_symbol: str = Field(min_length=1, max_length=10)
    distance_unit: Literal['km', 'miles'] = 'km'
    minimum_service_percent: Decimal = Field(default=0, ge=0, le=100, decimal_places=2)
    maximum_service_percent: Decimal = Field(default=100, ge=0, le=100, decimal_places=2)
    is_active: bool = True

    @model_validator(mode='after')
    def validate_limits(self):
        if self.maximum_service_percent < self.minimum_service_percent:
            raise ValueError('Service fee maximum must be at least the minimum')
        return self


class DistanceTier(FeeInput):
    up_to: Decimal | None = Field(default=None, gt=0, le=10000, allow_inf_nan=False)
    fee: Decimal = Money()
    per_unit: Decimal = Money(0)


class DeliverySettingsInput(FeeInput):
    state: str = Field(default='', max_length=100)
    city: str = Field(default='', max_length=100)
    base_fee: Decimal = Money()
    small_order_threshold: Decimal = Money()
    small_order_fee: Decimal = Money()
    free_delivery_threshold: Decimal | None = Money(None)
    free_delivery_max_distance: Decimal = Field(ge=0, le=10000, allow_inf_nan=False)
    service_fee_percent: Decimal = Field(default=0, ge=0, le=100, decimal_places=2, allow_inf_nan=False)
    distance_tiers: list[DistanceTier] = Field(min_length=1, max_length=30)
    active: bool = True

    @model_validator(mode='after')
    def validate_rules(self):
        self.state, self.city = self.state.strip().casefold(), self.city.strip().casefold()
        if self.city and not self.state:
            raise ValueError('Provide a state for city pricing')
        previous = Decimal(0)
        for index, tier in enumerate(self.distance_tiers):
            if tier.up_to is None:
                if index != len(self.distance_tiers) - 1:
                    raise ValueError('Only the final distance tier may be unlimited')
            elif tier.up_to <= previous:
                raise ValueError('Distance tiers must increase')
            else:
                previous = tier.up_to
        if self.distance_tiers[-1].up_to is not None:
            raise ValueError('Final distance tier must have up_to: null')
        return self


class SurgeInput(FeeInput):
    state: str = Field(default='', max_length=100)
    city: str = Field(default='', max_length=100)
    reason: Literal['rain', 'holiday', 'festival', 'peak_hours', 'high_demand', 'low_driver_availability']
    amount: Decimal = Money()
    active: bool = False
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @model_validator(mode='after')
    def validate_window(self):
        self.state, self.city = self.state.strip().casefold(), self.city.strip().casefold()
        if self.city and not self.state:
            raise ValueError('Provide a state for city surge')
        for name in ('starts_at', 'ends_at'):
            value = getattr(self, name)
            if value:
                if value.tzinfo is None:
                    raise ValueError('Surge dates require a timezone')
                setattr(self, name, value.astimezone(timezone.utc).replace(tzinfo=None))
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError('End must be after start')
        return self
