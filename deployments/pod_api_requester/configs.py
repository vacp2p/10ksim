from typing import Literal, Optional

from pydantic import BaseModel, NonNegativeInt


class Target(BaseModel):
    name: Optional[str] = None
    service: Optional[str] = None
    name_template: Optional[str] = None
    stateful_set: Optional[str] = None
    port: NonNegativeInt


class Endpoint(BaseModel):
    name: str
    headers: dict
    params: dict
    url: str
    type: Literal["POST", "GET"]
    paged: bool
