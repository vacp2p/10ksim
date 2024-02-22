# Python Imports
import logging
import pandas as pd
from itertools import chain
from typing import List, Dict
from pathlib import Path

# Project Imports
from src.metrics import scrape_utils
from result import Ok, Err, Result
from src.utils.file_utils import read_yaml_file
from src.utils.queries import get_query_data

logger = logging.getLogger(__name__)


class Scrapper:
    def __init__(self, url: str, query_config_file: str, out_folder: str):
        self._url = url
        self._query_config_file = query_config_file
        self._out_folder = out_folder
        self._set_query_config()
        # TODO make interval match value in cluster

    def query_and_dump_metrics(self):
        for metric_dict_item in self._query_config['metrics_to_scrape']:
            metric, column_name = next(iter(metric_dict_item.items()))
            logger.info(f'Querying {metric}')
            promql = self._create_query(metric, self._query_config['scrape_config'])

            match get_query_data(promql):
                case Ok(data):
                    logger.info(f'Successfully extracted {metric} data from response')
                case Err(err):
                    logger.info(err)
                    continue

            logger.info(f'Dumping {metric} data to .csv')
            self._dump_data(metric, column_name, data)

    def _set_query_config(self):
        self._query_config = read_yaml_file(self._query_config_file)

    def _create_query(self, metric: str, scrape_config: Dict) -> str:
        if '__rate_interval' in metric:
            metric = metric.replace('$__rate_interval', scrape_config['$__rate_interval'])
        promql = scrape_utils.create_promql(self._url, metric,
                                            scrape_config['until_hours_ago'],
                                            scrape_config['step'])

        return promql

    def _dump_data(self, metric: str, column_name: str, data: Dict):
        result = self._prepare_path(metric)
        if result.is_err():
            logger.error(f'{result.err_value}')
            exit(1)

        df = self._create_dataframe_from_data(data, column_name)
        df = self._sort_dataframe(df)

        df.to_csv(result.ok_value)
        logger.info(f'{metric} data dumped')

    def _prepare_path(self, metric: str) -> Result[Path, str]:
        output_file = f'{metric}.csv'
        output_dir = Path(self._out_folder)

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return Err(f'Error creating {output_dir}. {e}')

        return Ok(output_dir / output_file)

    def _create_dataframe_from_data(self, data: Dict, column_name: str) -> pd.DataFrame:
        final_df = pd.DataFrame()
        for pod_result_dict in data['result']:
            column_name_items = column_name.split('-')
            metric_result_info = pod_result_dict['metric']
            result_string = '_'.join(metric_result_info[key] for key in column_name_items)
            values = pod_result_dict['values']

            pod_df = self._create_pod_df(result_string, values)

            final_df = pd.merge(final_df, pod_df, how='outer', left_index=True, right_index=True)

        return final_df

    def _sort_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        columns = self._order(df.columns.tolist())
        df = df[columns]

        return df

    def _create_pod_df(self, column_name: str, values: List) -> pd.DataFrame:
        pod_df = pd.DataFrame(values, columns=['Unix Timestamp', column_name])
        pod_df['Unix Timestamp'] = pd.to_datetime(pod_df['Unix Timestamp'], unit='s')
        pod_df.set_index('Unix Timestamp', inplace=True)

        return pod_df

    # TODO this depends on pods name assigned in deployment
    def _order(self, column_names: List) -> List:
        def get_default_format_id(val):
            return int(val.split('-')[1].split('_')[0])

        nodes = []
        bootstrap = []
        others = []
        for column in column_names:
            if column.startswith('nodes'):
                nodes.append(column)
            elif column.startswith('bootstrap'):
                bootstrap.append(column)
            else:
                others.append(column)
        nodes.sort(key=get_default_format_id)
        bootstrap.sort(key=get_default_format_id)

        return list(chain(others, bootstrap, nodes))
