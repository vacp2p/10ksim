# Pyton Imports
import datetime


def create_promql(address: str, query: str, hours_passed: int, step: int) -> str:
    promql = address + "query_range?query=" + query

    start = datetime.datetime.timestamp(
        datetime.datetime.now() - datetime.timedelta(hours=hours_passed))
    now = datetime.datetime.timestamp(datetime.datetime.now())

    promql = (promql +
              "&start=" + str(start) +
              "&end=" + str(now) +
              "&step=" + str(step))

    return promql
