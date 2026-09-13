from pydantic import BaseModel, Field

class SessionRefresh(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=4096)
