# Python Imports
from datetime import timedelta
from pathlib import Path

# Project Imports
from pydantic import BaseModel, Field


class EventMapping(BaseModel):
    key: dict
    target: Path
    time_shift: timedelta = Field(default_factory=lambda: timedelta(0))
