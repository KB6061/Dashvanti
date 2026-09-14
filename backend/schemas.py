from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, EmailStr, Field, AliasChoices

Role = Literal['customer', 'restaurant', 'driver']

class Register(BaseModel):
    email: EmailStr
    password: str = Field(min_length=5)
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(max_length=30, default='')
    role: Role

class Login(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1)
    role: Role

class Forgot(BaseModel):
    email: EmailStr

class Reset(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(min_length=5)

class Profile(BaseModel):
    email: EmailStr | None = None
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(max_length=30, default='')

class AddressInput(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    details: str = Field(min_length=5, max_length=500)
    is_default: bool = False
    place_id: str | None = Field(default=None, max_length=255)

class AddressSelection(AddressInput):
    id: int | None = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class RestaurantInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(max_length=1000, default='')
    cuisine: str = Field(min_length=1, max_length=80)
    kind: Literal['restaurant', 'store'] = 'restaurant'
    address: str = Field(min_length=5, max_length=500)
    is_open: bool = False
    opening: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    closing: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    delivery_minutes: int = Field(ge=5, le=240)

class RestaurantHours(BaseModel):
    opening: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    closing: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')

class RestaurantAvailability(BaseModel):
    is_open: bool

class MenuInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(max_length=1000, default='')
    category: str = Field(max_length=80, default='General')
    price: Decimal = Field(gt=0, le=100000, decimal_places=2)
    veg: bool = True
    available: bool = True

class CartInput(BaseModel):
    special_instructions: str | None = Field(default=None, max_length=1000)
    menu_item_id: int
    quantity: int = Field(ge=0, le=50)

class OrderMode(BaseModel):
    mode: Literal['delivery', 'pickup']

class CustomerLocationInput(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    address: str | None = Field(default=None, max_length=500)

class CheckoutQuote(BaseModel):
    tip: Decimal = Field(default=Decimal("0"), ge=0, le=1000, decimal_places=2)
    mode: Literal['delivery', 'pickup']
    promo_code: str | None = Field(default=None, max_length=40)


class Checkout(CheckoutQuote):
    address_id: int | None = None
    request_key: str = Field(min_length=16, max_length=64)

class Transition(BaseModel):
    status: str = Field(max_length=40)

class Availability(BaseModel):
    online: bool

class DriverProfile(BaseModel):
    vehicle_type: str = Field(max_length=80, default='')
    vehicle_number: str = Field(max_length=80, default='')
    online: bool = False

class DriverLocationInput(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False, validation_alias=AliasChoices('latitude','lat'))
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False, validation_alias=AliasChoices('longitude','lng'))
    heading: float | None = Field(default=None, ge=0, le=360, allow_inf_nan=False)
    driver_id: int | None = Field(default=None, gt=0)
    order_id: int | None = Field(default=None, gt=0)

class ReviewInput(BaseModel):
    restaurant: int = Field(ge=1, le=5)
    driver: int | None = Field(default=None, ge=1, le=5)
    text: str = Field(min_length=1, max_length=2000)


class PresentationInput(BaseModel):
    cover_file_id: int | None = None
    logo_file_id: int | None = None
    gallery_file_ids: list[int] = Field(default_factory=list, max_length=12)
    busy_mode: Literal['open', 'busy', 'paused'] = 'open'
    busy_until: datetime | None = None
    prep_extra_minutes: int = Field(default=0, ge=0, le=120)
    capacity: int = Field(default=20, ge=1, le=100)

class BannerInput(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(max_length=500, default='')
    enabled: bool = False
    media_file_id: int | None = None

class PromotionInput(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(max_length=500, default='')
    code: str = Field(min_length=3, max_length=40, pattern=r'^[A-Za-z0-9_-]+$')
    percent: int = Field(ge=1, le=100)
    minimum: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=2)
    cap: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=2)
    first_order_only: bool = False
    enabled: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None

class TicketInput(BaseModel):
    order_id: int | None = None
    subject: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=5, max_length=2000)

class TicketUpdate(BaseModel):
    status: Literal['open', 'working', 'resolved']
    resolution: str = Field(max_length=2000, default='')

class MessageInput(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class AdminUserCreate(BaseModel):
    role: Role
    email: EmailStr
    password: str = Field(min_length=5, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(max_length=30, default='')
    order_mode: Literal['delivery', 'pickup'] = 'delivery'
    restaurant_name: str = Field(max_length=120, default='')
    description: str = Field(max_length=1000, default='')
    cuisine: str = Field(max_length=80, default='Indian')
    kind: Literal['restaurant', 'store'] = 'restaurant'
    address: str = Field(max_length=500, default='')
    is_open: bool = False
    opening: str = Field(default='09:00', pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    closing: str = Field(default='22:00', pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    delivery_minutes: int = Field(default=30, ge=5, le=240)
    online: bool = False
    vehicle_type: str = Field(max_length=80, default='')
    vehicle_number: str = Field(max_length=80, default='')


class AdminUserUpdate(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=5, max_length=128)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    order_mode: Literal['delivery', 'pickup'] | None = None
    restaurant_name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    cuisine: str | None = Field(default=None, min_length=1, max_length=80)
    kind: Literal['restaurant', 'store'] | None = None
    address: str | None = Field(default=None, max_length=500)
    is_open: bool | None = None
    opening: str | None = Field(default=None, pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    closing: str | None = Field(default=None, pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    delivery_minutes: int | None = Field(default=None, ge=5, le=240)
    online: bool | None = None
    vehicle_type: str | None = Field(default=None, max_length=80)
    vehicle_number: str | None = Field(default=None, max_length=80)

class FundRuleInput(BaseModel):
    method: Literal['flat', 'percent'] = 'flat'
    value: Decimal = Field(ge=0, le=100000, decimal_places=2)
    minimum: Decimal = Field(default=Decimal('0'), ge=0, le=100000, decimal_places=2)
    enabled: bool = True

class RefundInput(BaseModel):
    order_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, le=100000, decimal_places=2)
    reason: str = Field(min_length=3, max_length=500)

class QuickPayInput(BaseModel):
    order_id: int = Field(gt=0)
    payee_role: Literal['driver', 'restaurant']

class RoutePoint(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)

class RouteDistanceInput(BaseModel):
    origin: RoutePoint
    destination: RoutePoint

class OrderSoundPreference(BaseModel):
    enabled: bool

class DriverReassignment(BaseModel):
    driver_id: int
    expected_driver_id: int | None
    reason: str = Field(min_length=3, max_length=250)

class DriverStatusUpdate(Transition):
    order_id: int = Field(gt=0)

class CancellationPolicyInput(BaseModel):
    preparation_percent: int = Field(default=100, ge=0, le=100)
    review_threshold: int = Field(default=3, ge=2, le=100)

class CancellationInput(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    expected_status: str = Field(max_length=40)
    expected_refund: Decimal = Field(ge=0)
    expected_charge: Decimal = Field(ge=0)
    refund_override: Decimal | None = Field(default=None, ge=0)
