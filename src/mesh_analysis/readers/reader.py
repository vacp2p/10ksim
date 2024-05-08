# Python Imports
import pandas as pd
from abc import ABC, abstractmethod


class Reader(ABC):

    @abstractmethod
    def read(self) -> pd.DataFrame:
        pass
