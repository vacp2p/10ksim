# Python Imports
import socket
import logging
from typing import Dict
from result import Ok, Err
from kubernetes.client import CoreV1Api

# Project Imports
from src.metrics import scrape_utils
from src.metrics import kubernetes
from src.data.data_request_handler import DataRequestHandler
from src.utils.file_utils import read_yaml_file

logger = logging.getLogger(__name__)


class Scrapper:
    def __init__(self, api: CoreV1Api, url: str, query_config_file: str):
        self._url = url
        self._query_config = None
        self._query_config_file = query_config_file
        self._set_query_config()
        self._k8s = kubernetes.KubernetesManager(api)

    def query_and_dump_metrics(self):
        # https://github.com/kubernetes-client/python/blob/master/examples/pod_portforward.py
        socket.create_connection = self._k8s.create_connection

        for scrape_name, metric_config in self._query_config['metrics_to_scrape'].items():
            logger.info(f'Querying {scrape_name}')
            promql = self._create_query(metric_config['query'],
                                        self._query_config['scrape_config'])

            match scrape_utils.get_query_data(promql):
                case Ok(data):
                    logger.info(f'Successfully extracted {scrape_name} data from response')
                    file_location = (self._query_config['scrape_config']['dump_location'] +
                                     metric_config['folder_name'] +
                                     self._query_config['scrape_config']['simulation_name'])
                    self._dump_data(scrape_name, metric_config['extract_field'], data, file_location)
                case Err(err):
                    logger.info(err)
                    continue

    def _dump_data(self, scrape_name: str, extract_field: str, data: Dict, dump_path: str):
        logger.info(f'Dumping {scrape_name} data to .csv')
        data_handler = DataRequestHandler(data)
        data_handler.create_dataframe_from_request(extract_field)
        data_handler.dump_dataframe(dump_path)

    def _set_query_config(self):
        self._query_config = read_yaml_file(self._query_config_file)

    def _create_query(self, metric: str, scrape_config: Dict) -> str:
        if '__rate_interval' in metric:
            metric = metric.replace('$__rate_interval', scrape_config['$__rate_interval'])
        promql = scrape_utils.create_promql(self._url, metric,
                                            scrape_config['start_scrape'],
                                            scrape_config['finish_scrape'],
                                            scrape_config['step'])
        promql = promql.replace(" ", "%20")

        return promql
