# Python Imports
import logging
import requests
from typing import Dict
from result import Result, Err, Ok


logger = logging.getLogger(__name__)


def get_query_data(request: str) -> Result[Dict, str]:
    try:
        response = requests.get(request, timeout=30)
    except requests.exceptions.Timeout:
        return Err(f'Timeout error.')

    if response.ok:
        logger.info(f'Response: {response.status_code}')
        data = response.json()['data']
        return Ok(data)
    return Err(f'Error in query. Status code {response.status_code}. {response.content}')
