#!/usr/bin/env python3


import logging

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Builder(BaseModel):
    pass
