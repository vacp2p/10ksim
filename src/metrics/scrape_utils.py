# Pyton Imports
import json
import logging
import six.moves.urllib.request as urllib_request
from datetime import datetime
from result import Result, Ok, Err
from typing import Dict

logger = logging.getLogger(__name__)


def create_promql(address: str, query: str, start_scrape: str, finish_scrape: str, step: int) -> str:
    promql = address + "query_range?query=" + query

    start = datetime.strptime(start_scrape, "%Y-%m-%d %H:%M:%S").timestamp()
    end = datetime.strptime(finish_scrape, "%Y-%m-%d %H:%M:%S").timestamp()

    promql = (promql +
              "&start=" + str(start) +
              "&end=" + str(end) +
              "&step=" + str(step))

    return promql


def get_query_data(request: str) -> Result[Dict, str]:
    response = urllib_request.urlopen(request, timeout=30)

    if response.status == 200:
        logger.info(f'Response: {response.status}')
        data = json.loads(str(response.read(), 'utf-8'))
        return Ok(data)

    return Err(f"Error in query. Status code {response.status}. {response.read().decode('utf-8')}")
