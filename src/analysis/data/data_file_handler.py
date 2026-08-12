# Python Imports
import logging
from pathlib import Path
from typing import List, Optional

import pandas as pd
from pydantic import BaseModel
from result import Err, Ok, Result

# Project Imports
from src.analysis.data.data_handler import DataHandler
from src.analysis.utils import file_utils

logger = logging.getLogger(__name__)


class DataPath(BaseModel):
    name: str
    """Name associated with data (eg. experiment name)"""
    path: Path
    """Data path"""


class DataFileHandler(DataHandler):
    def __init__(self, ignore_columns: Optional[List] = None, include_files: Optional[List] = None):
        super().__init__(ignore_columns)
        self._include_files = include_files

    def concat_dataframes_from_folders_as_mean(self, folders: List, points: int):
        for folder in folders:
            folder_path = Path(folder)
            folder_df = pd.DataFrame()
            match file_utils.get_files_from_folder_path(
                folder_path, self._include_files, extension="csv"
            ):
                case Ok(data_files_names):
                    if not data_files_names:
                        self._report_no_csvs(folder_path)
                    folder_df = self._concat_files_as_mean(
                        folder_df, data_files_names, folder_path, points
                    )
                    folder_df["class"] = f"{folder_path.parent.name}/{folder_path.name}"
                    self._dataframe = pd.concat([self._dataframe, folder_df])
                case Err(error):
                    logger.error(error)

    @staticmethod
    def _report_no_csvs(path: Path) -> None:
        """Name the suffixless files, since scrapes taken before the .csv change have none."""
        stale = [p.name for p in path.iterdir() if p.is_file() and not p.name.startswith(".")]
        if stale:
            logger.error(
                f"{path} holds {len(stale)} file(s) with no .csv suffix ({', '.join(stale[:3])}"
                f"{', ...' if len(stale) > 3 else ''}); rename them with "
                f"`find {path} -type f ! -name '*.csv' -exec mv {{}} {{}}.csv \\;`"
            )
        else:
            logger.error(f"{path} holds no files to read.")

    def _concat_files_as_mean(
        self, target_df: pd.DataFrame, data_files_path: List, location: Path, points: int
    ) -> pd.DataFrame:
        for file_path in data_files_path:
            match self._concat_data_as_mean_from_file(target_df, location / file_path, points):
                case Ok(result_df):
                    logger.info(f"{file_path} added")
                    target_df = result_df
                case Err(msg):
                    logger.error(msg)

        return target_df

    def _concat_data_as_mean_from_file(
        self, target_df: pd.DataFrame, file_path: Path, points: int
    ) -> Result[pd.DataFrame, str]:
        if not file_path.exists():
            return Err(f"{file_path} cannot be dumped to memory.")

        logger.info(f"Reading {file_path} with {points} datapoints")
        file_df = pd.read_csv(file_path, parse_dates=["Time"], index_col="Time", nrows=points)
        if len(file_df) < points:
            logger.warning(f"Not enough datapoints in {file_path}")

        target_df = self.concat_data_as_mean(target_df, file_df, file_path.name)

        return Ok(target_df)

    def concat_dataframes_from_files(
        self,
        named_files: List[DataPath],
        group_name: str,
        points: int,
    ):
        for data_file in named_files:
            file_path = Path(data_file.path)
            if not file_path.exists():
                logger.error(f"{file_path} cannot be loaded.")
                continue

            logger.info(f"Reading {file_path} with {points} datapoints")
            file_df = pd.read_csv(file_path, parse_dates=["Time"], index_col="Time", nrows=points)
            if len(file_df) < points:
                logger.warning(f"Not enough datapoints in {file_path}")

            if self._ignore_columns:
                columns_to_drop = [
                    col
                    for col in file_df.columns
                    if any(col.startswith(prefix) for prefix in self._ignore_columns)
                ]
                if columns_to_drop:
                    logger.info(f"Dropping {len(columns_to_drop)} columns: {columns_to_drop}")
                    file_df = file_df.drop(columns=columns_to_drop)

            file_df = file_df.reset_index(drop=True)
            file_df["class"] = group_name
            file_df["variable"] = data_file.name
            self._dataframe = pd.concat([self._dataframe, file_df], ignore_index=True)
