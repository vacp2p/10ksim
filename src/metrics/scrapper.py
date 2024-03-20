# Python Imports
import logging
import socket
from typing import Dict
from kubernetes.client import CoreV1Api
from result import Ok, Err

from src.data.data_handler import DataHandler
# Project Imports
from src.metrics import scrape_utils
from src.metrics import kubernetes
from src.utils.file_utils import read_yaml_file

logger = logging.getLogger(__name__)


class Scrapper:
    def __init__(self, api: CoreV1Api,  url: str, query_config_file: str, out_folder: str):
        self._url = url
        self._query_config = None
        self._query_config_file = query_config_file
        self._out_folder = out_folder
        self._set_query_config()
        self._k8s = kubernetes.KubernetesManager(api)

    def query_and_dump_metrics(self):
        socket.create_connection = self._k8s.create_connection

        for metric_dict_item in self._query_config['metrics_to_scrape']:
            metric, column_name_placeholder = next(iter(metric_dict_item.items()))
            logger.info(f'Querying {metric}')
            promql = self._create_query(metric, self._query_config['scrape_config'])

            match scrape_utils.get_query_data(promql):
                case Ok(data):
                    logger.info(f'Successfully extracted {metric} data from response')
                    self._dump_data(metric, column_name_placeholder, data)
                case Err(err):
                    logger.info(err)
                    continue

    def _dump_data(self, metric: str, column_name_placeholders: str, data: Dict):
        logger.info(f'Dumping {metric} data to .csv')
        data_handler = DataHandler(data)
        data_handler.create_dataframe_from_request(column_name_placeholders)
        data_handler.dump_dataframe(self._out_folder, f'{metric}.csv')

    def _set_query_config(self):
        self._query_config = read_yaml_file(self._query_config_file)

    def _create_query(self, metric: str, scrape_config: Dict) -> str:
        if '__rate_interval' in metric:
            metric = metric.replace('$__rate_interval', scrape_config['$__rate_interval'])
        promql = scrape_utils.create_promql(self._url, metric,
                                            scrape_config['start_scrape'],
                                            scrape_config['finish_scrape'],
                                            scrape_config['step'])

        return promql
