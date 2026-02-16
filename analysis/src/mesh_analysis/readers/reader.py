# Python Imports
from abc import ABC, abstractmethod

import pandas as pd


class Reader(ABC):

    @abstractmethod
    def get_dataframes(self) -> pd.DataFrame:
        pass
