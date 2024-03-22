# Python Imports
import logging
import pandas as pd
from typing import List

# Project Imports
from src.data.data_handler import DataHandler
from src.utils import list

logger = logging.getLogger(__name__)


class DataRequestHandler(DataHandler):
    def __init__(self, data):
        super().__init__()
        self._raw_data = data
        self._dataframe = pd.DataFrame()

    def create_dataframe_from_request(self, placeholder):
        data_result = self._raw_data['data']['result']

        for pod_result_dict in data_result:
            final_column_name = self._extract_column_name_from_result(placeholder, pod_result_dict)
            values = pod_result_dict['values']

            pod_df = self._create_pod_df(final_column_name, values)

            self._dataframe = pd.merge(self._dataframe, pod_df, how='outer', left_index=True,
                                       right_index=True)

        self._sort_dataframe_columns()

    def _extract_column_name_from_result(self, placeholder, pod_result_dict):
        placeholder_items = placeholder.split('-')
        metric_info = pod_result_dict['metric']
        final_column_name = '_'.join(metric_info[key] for key in placeholder_items)

        return final_column_name

    def _create_pod_df(self, column_name: str, values: List) -> pd.DataFrame:
        pod_df = pd.DataFrame(values, columns=['Time', column_name])
        pod_df['Time'] = pd.to_datetime(pod_df['Time'], unit='s')
        pod_df.set_index('Time', inplace=True)

        return pod_df

    def _sort_dataframe_columns(self):
        columns = list.order_by_groups(self._dataframe.columns.tolist())
        self._dataframe = self._dataframe[columns]
