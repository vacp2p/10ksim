# Pyton Imports
import json
import logging
import urllib
from datetime import datetime
from typing import Dict

import six.moves.urllib.request as urllib_request
from result import Err, Ok, Result

logger = logging.getLogger(__name__)


def create_promql(
    address: str, query: str, start_scrape: str, finish_scrape: str, step: int
) -> str:
    query = urllib.parse.quote(query)
    promql = address + "query_range?query=" + query

    start = datetime.strptime(start_scrape, "%Y-%m-%d %H:%M:%S").timestamp()
    end = datetime.strptime(finish_scrape, "%Y-%m-%d %H:%M:%S").timestamp()

    promql = promql + "&start=" + str(start) + "&end=" + str(end) + "&step=" + str(step)

    return promql


def get_query_data(request: str) -> Result[Dict, str]:
    response = urllib_request.urlopen(request, timeout=30)

    if response.status != 200:
        return Err(
            f"Error in query. Status code {response.status}. {response.read().decode('utf-8')}"
        )

    logger.debug(f"Response: {response.status}")
    json_response = json.loads(str(response.read(), "utf-8"))

    if len(json_response["data"]["result"]) == 0:
        return Err(f"Returned data is empty.")

    return Ok(json_response)
