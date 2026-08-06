"""Vaclab processor - live node topology/resources snapshot taken from Prometheus.

Unlike the experiment/dataset/panel processors, this is not stored in MongoDB:
it's a live cluster-state snapshot, fetched fresh from Prometheus on every call.
"""

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from result import Err, Ok, Result

from dst_dashboard.config.data_structures import DataSourceConfig
from dst_dashboard.processors.prometheus_client import query_instant

logger = logging.getLogger(__name__)


class VaclabDataUnavailableError(Exception):
    """Raised when the datasource can't tell us which nodes even exist.

    Every other query degrades gracefully to "no data for this metric" per
    node, since the node set is already known. The uname query is different:
    it's what defines that node set in the first place, so its failure can't
    be silently treated as "zero nodes" - that would be indistinguishable
    from a real (empty) cluster and would hide a genuine outage.
    """


# patterns to exclude virtual devices, loopback, and other non-physical interfaces
NETWORK_DEVICE_EXCLUDE_REGEX = "lo|cilium.*|lxc.*|veth.*|docker.*|tunl.*|cali.*"

FILESYSTEM_TYPE_EXCLUDE_REGEX = "tmpfs|devtmpfs|overlay|squashfs"
# Root + the per-node /data volume are each node's real allocated capacity.
FILESYSTEM_MOUNTPOINT_REGEX = "^/(data)?$"

# System namespaces excluded from pod counts.
SYSTEM_NAMESPACE_EXACT = {
    "kube-system",
    "longhorn-system",
    "cert-manager",
    "kyverno",
    "authentik",
    "policy-reporter",
    "opentelemetry",
    "homepage",
    "dst-dashboard",
    "local",
}
SYSTEM_NAMESPACE_PREFIXES = (
    "cattle-",
    "victorialogs",
    "vmetrics",
    "fleet-",
    "cluster-fleet-",
    "p-",
    "u-",
)

RATE_WINDOW = "5m"


def is_system_namespace(namespace: str) -> bool:
    if namespace in SYSTEM_NAMESPACE_EXACT:
        return True
    return namespace.startswith(SYSTEM_NAMESPACE_PREFIXES)


def _vector_to_dict(vector: List[Dict[str, Any]], label_key: str) -> Dict[str, float]:
    """Turn an instant-query result vector into {label_value: float(value)}."""
    out: Dict[str, float] = {}
    for series in vector:
        key = series.get("metric", {}).get(label_key)
        value = series.get("value")
        if key is None or not value or len(value) < 2:
            continue
        try:
            out[key] = float(value[1])
        except (TypeError, ValueError):
            continue
    return out


def _build_instance_to_nodename(vector: List[Dict[str, Any]]) -> Dict[str, str]:
    """Every node the cluster is currently reporting, keyed by instance.

    Nodes are discovered live from this query rather than a hardcoded list.
    """
    mapping: Dict[str, str] = {}
    for series in vector:
        metric = series.get("metric", {})
        instance = metric.get("instance")
        nodename = metric.get("nodename")
        if instance and nodename:
            mapping[instance] = nodename
    return mapping


def _count_pods_per_node(vector: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for series in vector:
        metric = series.get("metric", {})
        node = metric.get("node")
        namespace = metric.get("namespace")
        if not node or not namespace:
            continue
        if is_system_namespace(namespace):
            continue
        counts[node] += 1
    return dict(counts)


def _build_cpu(
    instance: str, capacity_map: Dict[str, float], idle_fraction_map: Dict[str, float]
) -> Optional[Dict[str, float]]:
    capacity = capacity_map.get(instance)
    idle_fraction = idle_fraction_map.get(instance)
    if capacity is None or idle_fraction is None or capacity <= 0:
        return None
    used_cores = max(0.0, (1 - idle_fraction) * capacity)
    return {
        "used_cores": round(used_cores, 2),
        "capacity_cores": capacity,
        "used_percent": round(used_cores / capacity * 100, 2),
    }


def _build_memory(
    instance: str, total_map: Dict[str, float], available_map: Dict[str, float]
) -> Optional[Dict[str, float]]:
    total = total_map.get(instance)
    available = available_map.get(instance)
    if total is None or available is None or total <= 0:
        return None
    used = max(0.0, total - available)
    return {
        "used_bytes": int(used),
        "capacity_bytes": int(total),
        "used_percent": round(used / total * 100, 2),
    }


def _build_storage(
    instance: str, size_map: Dict[str, float], avail_map: Dict[str, float]
) -> Optional[Dict[str, float]]:
    size = size_map.get(instance)
    avail = avail_map.get(instance)
    if size is None or avail is None or size <= 0:
        return None
    used = max(0.0, size - avail)
    return {
        "used_bytes": int(used),
        "capacity_bytes": int(size),
        "used_percent": round(used / size * 100, 2),
    }


def _build_network(
    instance: str,
    rx_map: Dict[str, float],
    tx_map: Dict[str, float],
    capacity_map: Dict[str, float],
) -> Optional[Dict[str, Any]]:
    rx = rx_map.get(instance)
    tx = tx_map.get(instance)
    if rx is None or tx is None:
        return None
    capacity = capacity_map.get(instance)
    used = max(0.0, rx) + max(0.0, tx)
    used_percent = round(used / capacity * 100, 2) if capacity else None
    return {
        "rx_bytes_per_sec": round(rx, 2),
        "tx_bytes_per_sec": round(tx, 2),
        "used_bytes_per_sec": round(used, 2),
        "capacity_bytes_per_sec": capacity,
        "used_percent": used_percent,
    }


class VaclabProcessor:
    """Builds a live cluster node snapshot from a Prometheus datasource."""

    def __init__(self, datasource: DataSourceConfig):
        self.base_url = datasource.url

    def _run_queries(self, queries: Dict[str, str]) -> Dict[str, Result[List[Dict[str, Any]], str]]:
        """Runs every query concurrently, keeping each one's Ok/Err outcome
        intact - callers decide per-query whether a failure is fatal
        (uname) or something to gracefully degrade (everything else)."""
        results: Dict[str, Result[List[Dict[str, Any]], str]] = {}
        with ThreadPoolExecutor(max_workers=len(queries)) as executor:
            future_to_key = {
                executor.submit(query_instant, self.base_url, expr): key
                for key, expr in queries.items()
            }
            for future in as_completed(future_to_key):
                key = future_to_key[future]
                try:
                    results[key] = future.result()
                except Exception as e:
                    logger.error(f"Prometheus query '{key}' raised: {e}")
                    results[key] = Err(str(e))
        return results

    @staticmethod
    def _unwrap_or_empty(
        outcome: Result[List[Dict[str, Any]], str], key: str
    ) -> List[Dict[str, Any]]:
        """For non-critical queries: log and degrade to empty on failure."""
        match outcome:
            case Ok(vector):
                return vector
            case Err(reason):
                logger.warning(f"Prometheus query '{key}' returned no data: {reason}")
                return []

    def get_snapshot(self) -> Dict[str, Any]:
        queries = {
            "uname": "node_uname_info",
            "cpu_capacity": 'count(node_cpu_seconds_total{mode="idle"}) by (instance)',
            "cpu_idle_fraction": (
                f'avg(rate(node_cpu_seconds_total{{mode="idle"}}[{RATE_WINDOW}])) by (instance)'
            ),
            "mem_total": "node_memory_MemTotal_bytes",
            "mem_available": "node_memory_MemAvailable_bytes",
            "net_rx": (
                f'max(rate(node_network_receive_bytes_total{{device!~"{NETWORK_DEVICE_EXCLUDE_REGEX}"}}'
                f"[{RATE_WINDOW}])) by (instance)"
            ),
            "net_tx": (
                f'max(rate(node_network_transmit_bytes_total{{device!~"{NETWORK_DEVICE_EXCLUDE_REGEX}"}}'
                f"[{RATE_WINDOW}])) by (instance)"
            ),
            "net_capacity": (
                f'max(node_network_speed_bytes{{device!~"{NETWORK_DEVICE_EXCLUDE_REGEX}"}} > 0) by (instance)'
            ),
            "pods": "kube_pod_info",
            "fs_size": (
                f'sum(node_filesystem_size_bytes{{fstype!~"{FILESYSTEM_TYPE_EXCLUDE_REGEX}",'
                f'mountpoint=~"{FILESYSTEM_MOUNTPOINT_REGEX}"}}) by (instance)'
            ),
            "fs_avail": (
                f'sum(node_filesystem_avail_bytes{{fstype!~"{FILESYSTEM_TYPE_EXCLUDE_REGEX}",'
                f'mountpoint=~"{FILESYSTEM_MOUNTPOINT_REGEX}"}}) by (instance)'
            ),
        }

        results = self._run_queries(queries)

        match results["uname"]:
            case Ok(uname_vector):
                instance_to_nodename = _build_instance_to_nodename(uname_vector)
            case Err(reason):
                raise VaclabDataUnavailableError(
                    f"Unable to identify cluster nodes (uname query failed): {reason}"
                )

        unwrap = self._unwrap_or_empty
        cpu_capacity = _vector_to_dict(unwrap(results["cpu_capacity"], "cpu_capacity"), "instance")
        cpu_idle_fraction = _vector_to_dict(
            unwrap(results["cpu_idle_fraction"], "cpu_idle_fraction"), "instance"
        )
        mem_total = _vector_to_dict(unwrap(results["mem_total"], "mem_total"), "instance")
        mem_available = _vector_to_dict(
            unwrap(results["mem_available"], "mem_available"), "instance"
        )
        net_rx = _vector_to_dict(unwrap(results["net_rx"], "net_rx"), "instance")
        net_tx = _vector_to_dict(unwrap(results["net_tx"], "net_tx"), "instance")
        net_capacity = _vector_to_dict(unwrap(results["net_capacity"], "net_capacity"), "instance")
        fs_size = _vector_to_dict(unwrap(results["fs_size"], "fs_size"), "instance")
        fs_avail = _vector_to_dict(unwrap(results["fs_avail"], "fs_avail"), "instance")
        pod_counts = _count_pods_per_node(unwrap(results["pods"], "pods"))

        nodes = []
        for instance, hostname in sorted(instance_to_nodename.items(), key=lambda kv: kv[1]):
            nodes.append(
                {
                    "hostname": hostname,
                    "short_name": hostname.split(".")[0],
                    "cpu": _build_cpu(instance, cpu_capacity, cpu_idle_fraction),
                    "memory": _build_memory(instance, mem_total, mem_available),
                    "storage": _build_storage(instance, fs_size, fs_avail),
                    "network": _build_network(instance, net_rx, net_tx, net_capacity),
                    "pod_count": pod_counts.get(hostname, 0),
                }
            )

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "switch": {"id": "cilium-overlay", "label": "Cilium Geneve Overlay"},
            "nodes": nodes,
        }
