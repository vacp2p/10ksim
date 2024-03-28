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

    def add_dataframes_from_folders_as_mean(self, folder_paths: List) -> Result[List, str]:
        for folder in folder_paths:
            folder = Path(folder)
            match file_utils.get_files_from_folder_path(folder):
                case Ok(data_files_names):
                    self._add_files_as_mean(data_files_names, folder)
                    self._dataframe["class"] = str(folder.parents[0]) + folder.name
                    return Ok(folder_paths)
                case Err(error):
                    return Err(error)

    def _add_files_as_mean(self, data_files_path: List, location: Path):
        for file_path in data_files_path:
            match self.add_dataframe_from_file_as_mean(location / file_path):
                case Ok(msg):
                    logger.info(msg)
                case Err(msg):
                    logger.error(msg)

    def add_dataframe_from_file_as_mean(self, file_path: Path) -> Result[Path, str]:
        if file_path.exists():
            self._dump_mean_df(file_path)
            return Ok(file_path)

        return Err(f"{file_path} cannot be dumped to memory.")

    def _dump_mean_df(self, file_path: Path):
        df = pd.read_csv(file_path, parse_dates=['Time'], index_col='Time')
        df_mean = df.mean()
        df_mean = pd.DataFrame(df_mean, columns=[file_path.name])
        self._dataframe = pd.concat([self._dataframe, df_mean], axis=1)
