# Python Imports
import logging
import pandas as pd
from pathlib import Path
from typing import List
from result import Result, Ok, Err

# Project Imports
from src.utils import file_utils
from src.data.data_handler import DataHandler

logger = logging.getLogger(__name__)


class DataFileHandler(DataHandler):
    def __init__(self):
        super().__init__()
        self._dataframe = pd.DataFrame()

    def add_dataframes_from_folders_as_mean(self, folder_paths: List) -> Result[str, str]:
        for folder in folder_paths:
            folder = Path(folder)
            match file_utils.get_files_from_folder_path(folder):
                case Ok(data_files_names):
                    self._add_files_as_mean(data_files_names, folder)
                    # TODO: set class with yaml upgrades
                    self._dataframe["class"] = str(folder.parents[0]) + folder.name
                    msg = f"{folder_paths} added."
                    return Ok(msg)
                case Err(error):
                    return Err(error)

    def _add_files_as_mean(self, data_files_path: List, location: Path):
        for file_path in data_files_path:
            match self.add_dataframe_from_file_as_mean(location / file_path):
                case Ok(msg):
                    logger.info(msg)
                case Err(msg):
                    logger.error(msg)

    def add_dataframe_from_file_as_mean(self, file_path: Path) -> Result[str, str]:
        if file_utils.check_if_path_exists(file_path):
            self._dump_mean_df(file_path)
            return Ok(f"{file_path} dumped to memory.")

        return Err(f"{file_path} cannot be dumped to memory.")

    def get_dataframe(self) -> pd.DataFrame:
        return self._dataframe

    def _dump_mean_df(self, file_path: Path):
        df = pd.read_csv(file_path, parse_dates=['Time'], index_col='Time')
        file_name = file_utils.get_file_name_from_path(file_path)
        df_mean = df.mean()
        df_mean = pd.DataFrame(df_mean, columns=[file_name])
        self._dataframe = pd.concat([self._dataframe, df_mean], axis=1)

