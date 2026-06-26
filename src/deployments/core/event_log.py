# Python Imports
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Tuple, Union

# Project Imports
from src.utils.dict_utils import dict_partial_compare, dict_set


def find_events(
    log_path: Union[str, Path],
    key: Dict[str, str],
) -> Iterator[dict]:
    """
    Return a list of all events where all keys match `key`.
    Each line in `log_path` is converted to an event (dict).
    If the event contains all of the (key, value) items from key,
    then the event is converted to a new value using `extract(event)`
    """
    results = []
    with Path(log_path).open("r") as events_log:
        for line in events_log:
            event = json.loads(line)
            if dict_partial_compare(event, key):
                results.append(event)
    return results


def parse_events_log(
    log_path: Union[str, Path],
    events_list: List[Tuple[Dict[str, str], Union[str, Path]]],
    *,
    extract: Callable[[dict], Any] | None = None,
) -> dict:
    """
    Return a new dict constructed by parsing the event log.
    Each line in `log_path` is converted to an event (dict).
    If the event contains all of the (key, value) items from a dict in `events_list`,
    then the event is converted to a new value using `extract(event)` and added at `path` in the new dict,
    where `path` is the value from the `events_list`.

    :param log_path: Path to events log.
    :param events_list: List of tuples mapping a dict to compare to the line to a path in the return dict.
    :param extract: A function mapping the json loaded from the event log to the value in the return dict.
    :return: dict constructed from extracting matchign lines from log_path and converting them to values using `extract`.
    :rtype: dict
    """
    if extract is None:
        extract = lambda event: datetime.strptime(event["timestamp"], "%Y-%m-%d %H:%M:%S")
    return_dict = {}
    with Path(log_path).open("r") as events_log:
        for line in events_log:
            event = json.loads(line)
            for key, path in events_list:
                try:
                    if dict_partial_compare(event, key):
                        new_value = extract(event)
                        dict_set(
                            return_dict,
                            path,
                            new_value,
                            sep=".",
                        )
                except KeyError:
                    pass
    return return_dict
