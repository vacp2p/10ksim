# Python Imports
import logging
import pandas as pd
from typing import List

# Project Imports
from src.utils import path

logger = logging.getLogger(__name__)


class DataHandler:
    def __init__(self):
        self._dataframe = None

    @staticmethod
    def concatenate_dataframes(dataframes: List, vertically: bool = True) -> pd.DataFrame:
        if vertically:
            return pd.concat(dataframes)

        return pd.concat(dataframes, axis="columns")

    @staticmethod
    def prepare_dataframe_for_boxplot(dataframe: pd.DataFrame, class_name='class') -> pd.DataFrame:
        prepared_df = pd.melt(dataframe, class_name)

        return prepared_df

    def dump_dataframe(self, out_folder: str, file_name: str):
        result = path.prepare_path(out_folder, file_name)
        if result.is_err():
            logger.error(f'{result.err_value}')
            exit(1)

        self._dataframe.to_csv(result.ok_value)
        logger.info(f'{file_name} data dumped')