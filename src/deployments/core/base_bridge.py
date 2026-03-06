import json
import logging
from collections import defaultdict
from typing import Literal, Union

from kubernetes.client import (
    V1CronJob,
    V1DaemonSet,
    V1Deployment,
    V1Job,
    V1Pod,
    V1PodTemplateSpec,
    V1StatefulSet,
)

V1Deployable = Union[
    V1PodTemplateSpec,
    V1Pod,
    V1Deployment,
    V1StatefulSet,
    V1DaemonSet,
    V1Job,
    V1CronJob,
]

from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Tuple

from core.kube_utils import dict_apply, dict_get, dict_partial_compare, dict_set, dict_visit
from kubernetes.client import V1PodTemplateSpec, V1StatefulSet
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

PROJ_ROOT = Path(__file__).parent.parent.parent


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
    log_path: str,
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
    with open(log_path, "r") as events_log:
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


def format_timestamp_vquery(input_timestamp) -> str:
    """Format a timestamp for use in Victoria queries."""
    try:
        return input_timestamp.strftime("%Y-%m-%dT%H:%M:%S")
    except (AttributeError, TypeError):
        pass


def format_timestamp_url(node):
    """Format a timestamp for use in Grafana or Victoria clickable urls."""
    try:
        return node.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    except AttributeError:
        pass


def format_metadata_timestamps(metadata: dict, format: Literal["vquery", "url"]) -> dict:
    formater_map = {"vquery": format_timestamp_vquery, "url": format_timestamp_url}
    try:
        return dict_apply(metadata, formater_map[format])
    except KeyError as e:
        raise ValueError(f"Unknown format option passed to function. format: `{format}`") from e


def get_valid_shifted_times(deltatime_map: Dict[str, timedelta], metadata: dict) -> dict:
    shifted = deepcopy(metadata)
    for path, delta in deltatime_map.items():
        time_value = dict_get(shifted, path, default=None, sep=".")
        if time_value is not None:
            shifted_time = time_value + delta
            dict_set(shifted, path, shifted_time, sep=".", replace_leaf=True)

    filtered = {}

    def filter(path, obj):
        try:
            start_dt = obj["start"]
            end_dt = obj["end"]
            if end_dt <= start_dt:
                return
            dict_set(filtered, path / "start", start_dt)
            dict_set(filtered, path / "end", end_dt)
        except (KeyError, TypeError) as e:
            pass

    dict_visit(shifted, filter)

    return filtered


def add_links(metadata, links_map):
    # For interval_type in [completed, stable] (if they were added).
    for interval_type in metadata.keys():
        try:
            for link_type, base in links_map.items():
                metadata[interval_type][link_type] = base.format(
                    start=metadata[interval_type]["start"], end=metadata[interval_type]["end"]
                )
        except KeyError:
            pass


class EventMapping(BaseModel):
    key: dict
    target: Path
    time_shift: timedelta = Field(default_factory=lambda: timedelta(0))


class BaseBridge(BaseModel):
    statefulsets_key: str = "stateful_sets"
    nodes_key: str = "nodes_per_statefulset"

    def _get_metadata_from_events_list(
        self, events_log_path: str, events_list: List[EventMapping]
    ) -> dict:
        """Extract events in from a given event log."""
        # Strip the timedelta for the conversion, to get a list of Tuple[match_dict : dict, path : str].
        events_maps = [(obj.key, obj.target) for obj in events_list]
        metadata = parse_events_log(events_log_path, events_maps)

        # Get timedeltas for each path. dict of {path : timedelta}.
        deltatime_map = {obj.target: obj.time_shift for obj in events_list}
        shifted = get_valid_shifted_times(deltatime_map, metadata)
        metadata.update(shifted)

        metadata = format_metadata_timestamps(metadata, "vquery")

        return metadata

    def get_metadata(self, events_log: Path) -> dict:
        all_metadata = self._aggregate_metadata_events(events_log)

        # Extract from all metadata and put into the following structure.
        map = {
            "stack": [self.statefulsets_key, self.nodes_key, "namespace"],
            "experiment": ["experiment_name", "experiment_class"],
            "metadata": ["command", "kube_config", "namespace", "namespaces", "args"],
        }
        metadata = defaultdict(dict)
        for main_key, sub_keys in map.items():
            for sub_key in sub_keys:
                try:
                    metadata[main_key][sub_key] = all_metadata[sub_key]
                except KeyError:
                    pass

        metadata["stack"]["extra_fields"] = ["kubernetes.pod_name", "kubernetes.pod_node_name"]
        metadata["metadata"]["subdir"] = events_log.relative_to(PROJ_ROOT)
        metadata["stack"]["name"] = self._get_name(metadata)
        try:
            metadata["params"] = all_metadata["params"]
        except KeyError:
            pass
        return dict(metadata)

    def _get_name(self, metadata: dict):
        counts = metadata["stack"][self.nodes_key]
        sets = metadata["stack"][self.statefulsets_key]
        nodes_str = "__".join(f"{set}_{count}" for set, count in zip(sets, counts))
        return f"{metadata['experiment']['experiment_name']}__{nodes_str}"

    def _aggregate_metadata_events(self, events_log: Path) -> dict:
        """Collect all metadata from events log, and gather StatefulSet deployments."""
        metadata = {}
        namespaces = set()

        # Create list of all deployed StatefulSets to plug into analysis script.
        metadata[self.statefulsets_key] = []
        metadata[self.nodes_key] = []
        for event in find_events(
            events_log, {"event": "deployment", "phase": "start", "kind": "StatefulSet"}
        ):
            metadata[self.statefulsets_key].append(event["name"])
            metadata[self.nodes_key].append(event["replicas"])
            namespaces.add(event["namespace"])

        if len(namespaces) == 1:
            metadata["namespace"] = next(iter(namespaces))
        else:
            logger.warning(f"Multiple namespaces used. namespaces: `{namespaces}`")
            metadata["namespaces"] = list(namespaces)

        for event in find_events(events_log, {"event": "metadata"}):
            metadata.update(event)

        return metadata
