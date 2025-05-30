# Python Imports
from abc import ABC, abstractmethod
from typing import List, Optional

# Project Imports


class MessageTracer(ABC):
    """Abstract class for working with raw message patterns from Victoria."""

    def __init__(self, extra_fields: List[str]):
        self._patterns: Optional[List] = None
        self._tracings: Optional[List] = None
        self._extra_fields = extra_fields

    @property
    @abstractmethod
    def patterns(self) -> List:
        pass

    @abstractmethod
    def trace(self, parsed_logs: List) -> List:
        pass

    @abstractmethod
    def get_num_patterns_group(self) -> int:
        pass

    @abstractmethod
    def get_extra_fields(self) -> List[str]:
        pass
