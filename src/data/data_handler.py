# Python Imports
import logging
import pandas as pd
from pathlib import Path

# Project Imports
from src.utils import path

logger = logging.getLogger(__name__)


class DataHandler:
    def __init__(self):
        self._dataframe = None

    @staticmethod
    def prepare_dataframe_for_boxplot(dataframe: pd.DataFrame, class_name='class') -> pd.DataFrame:
        prepared_df = pd.melt(dataframe, class_name)

        return prepared_df

    @staticmethod
    def add_file_as_mean_to_df(target_df: pd.DataFrame, file_path: Path):
        df = pd.read_csv(file_path, parse_dates=['Time'], index_col='Time')
        df_mean = df.mean()
        df_mean = pd.DataFrame(df_mean, columns=[file_path.name])
        target_df = pd.concat([target_df, df_mean], axis=1)

        return target_df

    @property
    def dataframe(self) -> pd.DataFrame:
        return self._dataframe

    def dump_dataframe(self, dump_path: str):
        result = path.prepare_path(dump_path)
        if result.is_err():
            logger.error(f'{result.err_value}')
            exit(1)

        self._dataframe.to_csv(result.ok_value)
        logger.info(f'{dump_path} data dumped')
