# Python Imports
import logging
import pandas as pd
from pathlib import Path
from typing import List, Optional
from result import Result, Ok, Err

# Project Imports
from src.utils import file_utils
from src.data.data_handler import DataHandler

logger = logging.getLogger(__name__)


class DataFileHandler(DataHandler):

    def concat_dataframes_from_folders_as_mean(self, folders: List, points: int):
        for folder in folders:
            folder_path = Path(folder)
            folder_df = pd.DataFrame()
            match file_utils.get_files_from_folder_path(folder_path):
                case Ok(data_files_names):
                    folder_df = self._concat_files_as_mean(folder_df, data_files_names, folder_path,
                                                           points)
                    folder_df["class"] = f"{folder_path.parent.name}/{folder_path.name}"
                    self._dataframe = pd.concat([self._dataframe, folder_df])
                case Err(error):
                    logger.error(error)

    def _concat_files_as_mean(self, target_df: pd.DataFrame, data_files_path: List,
                              location: Path, points: int) -> pd.DataFrame:
        for file_path in data_files_path:
            match self._concat_data_as_mean_from_file(target_df, location / file_path, points):
                case Ok(result_df):
                    logger.info(f"{file_path} added")
                    target_df = result_df
                case Err(msg):
                    logger.error(msg)

        return target_df

    def _concat_data_as_mean_from_file(self, target_df: pd.DataFrame, file_path: Path,
                                       points: int) -> Result[pd.DataFrame, str]:
        if not file_path.exists():
            return Err(f"{file_path} cannot be dumped to memory.")

        logger.info(f'Reading {file_path} with {points} datapoints')
        file_df = pd.read_csv(file_path, parse_dates=['Time'], index_col='Time', nrows=points)
        if len(file_df) < points:
            logger.warning(f'Not enough datapoints in {file_path}')

        target_df = self.concat_data_as_mean(target_df, file_df, file_path.name)

        return Ok(target_df)
