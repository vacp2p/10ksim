# Python Imports
from copy import deepcopy
from datetime import timedelta
from typing import Dict, Literal

# Project Imports
from src.utils.dict_utils import dict_apply, dict_get, dict_set, dict_visit


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
        except (KeyError, TypeError):
            pass

    dict_visit(shifted, filter)

    return filtered


def add_links(metadata, links_map):
    # For interval_type in [completed, stable] (if they were added).
    for interval_type in metadata.keys():
        try:
            for link_type, base in links_map.items():
                metadata[interval_type][link_type] = base.format(
                    start=metadata[interval_type]["start"],
                    end=metadata[interval_type]["end"],
                )
        except KeyError:
            pass
