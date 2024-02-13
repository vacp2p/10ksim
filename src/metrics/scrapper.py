# Python Imports
import requests
from typing import List
import logging

# Project Imports
import src.logging.logger
from src.metrics import scrape_utils

logger = logging.getLogger(__name__)


class Scrapper:
    def __init__(self, url: str, namespace: str, metrics: List):
        self._url = url
        self._namespace = namespace
        self._metrics = metrics
        # TODO make interval match value in cluster
        self._template = "irate($metric{namespace=$namespace}[3m])"

    def make_queries(self):
        for metric in self._metrics:
            query = self._template.replace("$metric", metric)
            query = query.replace("$namespace", self._namespace)
            promql = scrape_utils.create_promql(self._url, query, 1, 60)
            logger.info(f"Promql: {promql}")
            response = requests.get(promql)
            logger.info(f"Response: {response.status_code}")




