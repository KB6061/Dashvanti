from pydantic import BaseModel, Field, StrictBool, field_validator


class AgreementRead(BaseModel):
    agreement_version: str = Field(min_length=1, max_length=40)
    scroll_completed: StrictBool


class AgreementAccept(BaseModel):
    agreement_version: str = Field(min_length=1, max_length=40)
    full_legal_name: str = Field(min_length=2, max_length=160)
    acknowledgements: dict[str, StrictBool]

    @field_validator('full_legal_name')
    @classmethod
    def legal_name(cls, value):
        value = ' '.join(value.split())
        if len(value) < 2 or not any(c.isalpha() for c in value) or any(ord(c) < 32 for c in value):
            raise ValueError('Enter your full legal name')
        return value
