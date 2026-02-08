import logging
from typing import Dict, List, Optional

from result import Err, Ok

from src.analysis.data.data_request_handler import DataRequestHandler
from src.analysis.metrics import kubernetes_manager, scrape_utils
from src.analysis.metrics.config import NewScrapeConfig

logger = logging.getLogger(__name__)


class Scrapper:
    def __init__(self, kube_config: str, url: str, config: NewScrapeConfig):
        self._url = url
        self._scrape_config = config
        self._k8s = kubernetes_manager.KubernetesManager(kube_config)

    def query_and_dump_metrics(self):
        # https://github.com/kubernetes-client/python/blob/master/examples/pod_portforward.py
        # socket.create_connection = self._k8s.create_connection
        # Not needed anymore as we have a public address in the lab

        # for time_name in self._query_config["general_config"]["times_names"]:
        logger.info(f"Querying simulation {self._scrape_config.name}")
        for metric_config in self._scrape_config.metrics_to_scrape:
            logger.info(f"Querying metric {metric_config.name}")
            promql = self._create_query(metric_config.query, self._scrape_config["scrape_config"])
            logger.debug(f"Query: {promql}")
            match scrape_utils.get_query_data(promql):
                case Ok(data):
                    logger.debug(f"Successfully extracted {metric_config.name} data from response")
                    file_location = (
                        self._scrape_config.dump_location
                        / metric_config.folder_name
                        / self._scrape_config.name
                    ).as_posix()
                    self._dump_data(
                        metric_config.name,
                        metric_config.extract_field,
                        metric_config.get("container", None),
                        metric_config.get("metrics_path", None),
                        data,
                        file_location,
                    )
                case Err(err):
                    logger.error(f"Error in {metric_config.name}. {err}")
                    continue

    def _dump_data(
        self,
        scrape_name: str,
        extract_field: str,
        container_name: Optional[str],
        metrics_path: Optional[str],
        data: Dict,
        dump_path: str,
    ):
        logger.debug(f"Dumping {scrape_name} data to .csv")
        data_handler = DataRequestHandler(data)
        data_handler.create_dataframe_from_request(extract_field, container_name, metrics_path)
        data_handler.dump_dataframe(dump_path)

    def _create_query(self, metric: str, scrape_config: NewScrapeConfig) -> str:
        if "__rate_interval" in metric:
            metric = metric.replace("$__rate_interval", scrape_config.rate_interval)
        promql = scrape_utils.create_promql(
            self._url, metric, scrape_config.start, scrape_config.end, scrape_config.step
        )

        return promql

    def _create_query_old(self, metric: str, scrape_config: Dict, time_name: List) -> str:
        if "__rate_interval" in metric:
            metric = metric.replace("$__rate_interval", scrape_config["rate_interval"])
        promql = scrape_utils.create_promql(
            self._url, metric, time_name[0], time_name[1], scrape_config["step"]
        )

        return promql
