# Python Imports
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Dict, Literal, Optional
from urllib.parse import quote, urlencode

# Project Imports
from src.utils.dict_utils import KeepNode, dict_get, dict_set, dict_transform, dict_visit


def format_timestamp_vquery(input_timestamp) -> str:
    """Format a timestamp for use in Victoria queries."""
    try:
        result = input_timestamp.strftime("%Y-%m-%dT%H:%M:%S")
        return result
    except (AttributeError, TypeError):
        raise KeepNode()


def format_timestamp_url(node):
    """Format a timestamp for use in Grafana or Victoria clickable urls."""
    try:
        return node.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    except AttributeError:
        raise KeepNode()


def format_metadata_timestamps(metadata: dict, format: Literal["vquery", "url"]) -> dict:
    formater_map = {"vquery": format_timestamp_vquery, "url": format_timestamp_url}
    try:
        return dict_transform(metadata, formater_map[format])
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

    def collect_valid_interval(path, obj):
        try:
            start_dt = obj["start"]
            end_dt = obj["end"]
            if end_dt <= start_dt:
                return
            dict_set(filtered, path / "start", start_dt)
            dict_set(filtered, path / "end", end_dt)
        except (KeyError, TypeError):
            pass

    dict_visit(shifted, collect_valid_interval)

    return filtered


def grafana_link(start_time: datetime, end_time: datetime, namespace: Optional[str] = None) -> str:
    base = "https://grafana.lab.vac.dev/d/jIrqsZTIz/nwaku"
    params = {
        "orgId": 1,
        "from": start_time.isoformat(),
        "to": end_time.isoformat(),
        "timezone": "utc",
        "refresh": "1m",
        "var-libp2p_peers_top5": "$__all",
        "var-libp2p_peers_bottom5": "$__all",
        "var-libp2p_traffic_in_top5": "$__all",
        "var-libp2p_traffic_in_bottom5": "$__all",
        "var-libp2p_traffic_out_top5": "$__all",
        "var-libp2p_traffic_out_bottom5": "$__all",
        "var-libp2p_open_streams_top5": "",
        "var-libp2p_open_streams_bottom5": "$__all",
        "var-container_network_receive_top5": "$__all",
        "var-container_network_receive_bottom5": "$__all",
        "var-container_network_transmit_top5": "",
        "var-container_network_transmit_bottom5": "$__all",
        "var-container_memory_usage_bytes_top5": "$__all",
        "var-container_memory_usage_bytes_bottom5": "$__all",
        "var-nim_gc_mem_bytes_bottom5": "$__all",
        "var-nim_gc_mem_bytes_top5": "$__all",
        "var-discv5_in_top5": "$__all",
        "var-discv5_in_bottom5": "$__all",
        "var-discv5_out_bottom5": "$__all",
        "var-discv5_out_top5": "$__all",
        "var-top_discv5_discovered": "$__all",
        "var-bottom_discv5_discovered": "$__all",
    }
    if namespace is not None:
        params["var-namespace"] = namespace
    return base + "?" + urlencode(params, doseq=True)


def victorialogs_link(start_time: datetime, end_time: datetime, namespace: Optional[str] = None):
    query = "kubernetes.pod_namespace:* | order by (_time)"
    if namespace is not None:
        query = f"kubernetes.pod_namespace:{namespace} | order by (_time)"

    delta = end_time - start_time
    total_seconds = max(0, int(delta.total_seconds()))
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    range_input = ""
    if hours:
        range_input += f"{hours}h"
    if minutes:
        range_input += f"{minutes}m"
    if seconds or not range_input:
        range_input += f"{seconds}s"

    params = {
        "query": query,
        "g0.range_input": range_input,
        "g0.end_input": end_time.replace(microsecond=0).isoformat(),
        "g0.relative_time": "none",
        "limit": 10000,
    }
    return "https://vlselect.lab.vac.dev/select/vmui/#/?" + urlencode(params, quote_via=quote)


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


def _is_interval_node(node: Any) -> bool:
    """
    True if `node` is a dict with 'start' and 'end' both being datetime objects.
    We do not check end > start here.
    """
    if not isinstance(node, dict):
        return False
    start = node.get("start")
    end = node.get("end")
    return isinstance(start, datetime) and isinstance(end, datetime)


def _format_duration(duration: timedelta) -> str:
    total_seconds = int(duration.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"


def _enrich_interval_node(node: Any, *, namespace: Optional[str]) -> Any:
    """
    If `node` is an interval dict with end > start:
      - format timestamps for vquery,
      - add duration, grafana, victoria_logs.
    Otherwise: leave unchanged.
    """
    if not _is_interval_node(node):
        raise KeepNode()

    start = node["start"]
    end = node["end"]

    if end < start:
        raise KeepNode()

    return {
        **node,
        "start": format_timestamp_vquery(start),
        "end": format_timestamp_vquery(end),
        "duration": _format_duration(end - start),
        "grafana": grafana_link(start, end, namespace),
        "victoria_logs": victorialogs_link(start, end, namespace),
    }


def enrich_intervals(metadata: Dict[str, Any], *, namespace: Optional[str]) -> Dict[str, Any]:
    """
    Return a new metadata dict where every valid interval node (end > start) is:
      - formatted via format_timestamp_vquery,
      - enriched with duration, grafana, victoria_logs.
    Invalid or incomplete intervals are left unchanged.
    """

    def transform(node: Any) -> Any:
        return _enrich_interval_node(node, namespace=namespace)

    return dict_transform(metadata, transform)
