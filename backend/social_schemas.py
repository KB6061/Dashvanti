from pydantic import BaseModel, Field


class GoogleLogin(BaseModel):
    id_token: str = Field(min_length=20, max_length=16384)
    csrf_token: str = Field(min_length=32, max_length=128)


class FacebookLogin(BaseModel):
    access_token: str = Field(min_length=20, max_length=8192)
    csrf_token: str = Field(min_length=32, max_length=128)
