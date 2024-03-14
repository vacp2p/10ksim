# Pyton Imports
from datetime import datetime


# Having now in an external function allows us to mock it in the tests
def _get_datetime_now() -> datetime:
    return datetime.now()


def create_promql(address: str, query: str, start_scrape: str, finish_scrape: str, step: int) -> str:
    promql = address + "query_range?query=" + query

    start = datetime.strptime(start_scrape, "%Y-%m-%d %H:%M:%S").timestamp()
    end = datetime.strptime(finish_scrape, "%Y-%m-%d %H:%M:%S").timestamp()

    promql = (promql +
              "&start=" + str(start) +
              "&end=" + str(end) +
              "&step=" + str(step))

    return promql
