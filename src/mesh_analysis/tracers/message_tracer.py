# Python Imports
import pandas as pd
from abc import ABC, abstractmethod
from typing import List


# Project Imports


class MessageTracer(ABC):

    @abstractmethod
    def __init__(self):
        self._patterns = None
        pass

    @property
    def patterns(self) -> List:
        return self._patterns

    @abstractmethod
    def trace(self, parsed_logs: List) -> pd.DataFrame:
        pass
