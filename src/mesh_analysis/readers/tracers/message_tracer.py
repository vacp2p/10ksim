# Python Imports
from abc import ABC, abstractmethod
from typing import List, Optional

# Project Imports


class MessageTracer(ABC):

    def __init__(self):
        self._patterns: Optional[List] = None

    @property
    def patterns(self) -> List:
        return self._patterns

    @abstractmethod
    def trace(self, parsed_logs: List) -> List:
        pass

    @abstractmethod
    def get_num_patterns(self) -> int:
        pass
