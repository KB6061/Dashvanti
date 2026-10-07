from datetime import date
from pydantic import BaseModel, EmailStr, Field

class AccountProfileInput(BaseModel):
    first_name: str = Field(min_length=1,max_length=80)
    last_name: str = Field(default='',max_length=80)
    email: EmailStr
    phone: str = Field(default='',max_length=30)
    date_of_birth: date | None = None
    gender: str = 'prefer_not_to_say'
    language: str = Field(default='en',max_length=20)
    country: str = Field(pattern=r'^(US|IN)$')
    state: str = Field(default='',max_length=100)
    city: str = Field(default='',max_length=100)
    timezone: str = Field(default='America/Chicago',max_length=80)
    theme: str = Field(default='system',pattern=r'^(light|dark|system)$')
    current_password: str = ''

class AccountActionInput(BaseModel):
    action: str = Field(max_length=40)
    data: dict = Field(default_factory=dict)

class AccountTwoFactorInput(BaseModel):
    challenge: str = Field(max_length=2000)
    code: str = Field(pattern=r'^\d{6}$')
