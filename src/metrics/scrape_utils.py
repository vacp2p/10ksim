# Pyton Imports
import datetime


# Having now in an external function allows us to mock it in the tests
def _get_datetime_now() -> datetime.datetime:
    return datetime.datetime.now()


def create_promql(address: str, query: str, hours_passed: int, step: int) -> str:
    promql = address + "query_range?query=" + query

    start = datetime.datetime.timestamp(
        _get_datetime_now() - datetime.timedelta(hours=hours_passed))
    now = datetime.datetime.timestamp(_get_datetime_now())

    promql = (promql +
              "&start=" + str(start) +
              "&end=" + str(now) +
              "&step=" + str(step))

    return promql
