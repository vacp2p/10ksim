# Python Imports
import pandas as pd
from abc import ABC, abstractmethod


class Reader(ABC):

    @abstractmethod
    def get_dataframes(self) -> pd.DataFrame:
        pass
