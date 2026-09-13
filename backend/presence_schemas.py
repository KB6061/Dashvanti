from typing import Literal
from pydantic import BaseModel

class DriverPresence(BaseModel):
    mode: Literal['ONLINE', 'BREAK', 'HOME']
