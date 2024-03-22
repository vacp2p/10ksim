# Python Imports
import logging
import pandas as pd
from result import Result, Ok, Err

# Project Imports
from src.utils import file_utils
from src.data.data_handler import DataHandler

logger = logging.getLogger(__name__)


class DataFileHandler(DataHandler):
    def __init__(self):
        super().__init__()
        self._dataframe = pd.DataFrame()

    def add_dataframes_from_folder_as_mean(self, folder_path: str) -> Result[str, str]:
        data_files_path = file_utils.get_files_from_folder_path(folder_path)

        for file_path in data_files_path:
            self.add_dataframe_from_file_as_mean(file_path)

        # TODO: set class with yaml upgrades
        self._dataframe["class"] = folder_path.split("/")[-2]

    def add_dataframe_from_file_as_mean(self, file_path: str) -> Result[str, str]:
        match file_utils.check_if_file_exists(file_path):
            case Ok(_):
                self._dump_mean_df(file_path)
                return Ok("")
            case Err(_):
                return Err("")

    def get_dataframe(self) -> pd.DataFrame:
        return self._dataframe

    def _dump_mean_df(self, file_path: str):
        df = pd.read_csv(file_path, parse_dates=['Time'], index_col='Time')
        file_name = file_utils.get_file_name_from_path(file_path)
        df_mean = df.mean()
        df_mean = pd.DataFrame(df_mean, columns=[file_name])
        self._dataframe = pd.concat([self._dataframe, df_mean], axis=1)

