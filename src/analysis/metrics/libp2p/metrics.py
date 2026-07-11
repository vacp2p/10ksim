from typing import Iterator

from src.analysis.metrics.config import MetricToScrape


def peers(namespace: str) -> MetricToScrape:
    return MetricToScrape(
        name="libp2p_peers",
        query=f"libp2p_peers{{namespace='{namespace}'}}",
        extract_field="instance",
        folder_name="libp2p-peers/",
    )


def open_streams(namespace: str) -> MetricToScrape:
    return MetricToScrape(
        name="libp2p_open_streams",
        query=f"libp2p_open_streams{{namespace='{namespace}'}}",
        extract_field="instance-type-dir",
        folder_name="libp2p-open-streams/",
    )


def network_in(namespace: str) -> MetricToScrape:
    return MetricToScrape(
        name="libp2p_network_in",
        query=f"rate(libp2p_network_bytes_total{{direction='in', namespace='{namespace}'}}[$__rate_interval])",
        extract_field="instance",
        folder_name="libp2p-in/",
    )


def network_out(namespace: str) -> MetricToScrape:
    return MetricToScrape(
        name="libp2p_network_out",
        query=f"rate(libp2p_network_bytes_total{{direction='out', namespace='{namespace}'}}[$__rate_interval])",
        extract_field="instance",
        folder_name="libp2p-out/",
    )


def container_recv_bytes(namespace: str) -> MetricToScrape:
    return MetricToScrape(
        name="container_recv_bytes",
        query=f"rate(container_network_receive_bytes_total{{namespace='{namespace}'}}[$__rate_interval])",
        extract_field="pod-node",
        folder_name="container-recv/",
    )


def container_sent_bytes(namespace: str) -> MetricToScrape:
    return MetricToScrape(
        name="container_sent_bytes",
        query=f"rate(container_network_transmit_bytes_total{{namespace='{namespace}'}}[$__rate_interval])",
        extract_field="pod-node",
        folder_name="container-sent/",
    )


def low_peers(namespace: str) -> MetricToScrape:
    return MetricToScrape(
        name="libp2p_low_peers",
        query=f"sum by(job) (libp2p_gossipsub_low_peers_topics{{namespace='{namespace}'}})",
        extract_field="job",
        folder_name="low-peers/",
    )


def high_peers(namespace: str) -> MetricToScrape:
    return MetricToScrape(
        name="libp2p_high_peers",
        query=f"sum by(job) (libp2p_gossipsub_healthy_peers_topics{{namespace='{namespace}'}})",
        extract_field="job",
        folder_name="high-peers/",
    )


def container_memory_bytes(namespace: str) -> MetricToScrape:
    # cadvisor emits both the pod cgroup total and a per-container series; `max by
    # (pod)` picks the pod total. `sum` would add them and roughly double the value.
    return MetricToScrape(
        name="container_memory_bytes",
        query=f"max by (pod) (container_memory_usage_bytes{{namespace='{namespace}'}})",
        extract_field="pod",
        folder_name="container-memory/",
    )


def nim_gc_memory_bytes(namespace: str) -> MetricToScrape:
    # nim_gc_mem_bytes is a gauge (heap in use), so rate() of it is meaningless;
    # sum the per-thread series for the pod total.
    return MetricToScrape(
        name="nim_gc_memory_bytes",
        query=f"sum by (pod) (nim_gc_mem_bytes{{namespace='{namespace}'}})",
        extract_field="pod",
        folder_name="nim-gc-memory/",
    )


def libp2p_metrics(namespace: str) -> Iterator[MetricToScrape]:
    yield peers(namespace)
    yield open_streams(namespace)
    yield network_in(namespace)
    yield network_out(namespace)
    yield container_recv_bytes(namespace)
    yield container_sent_bytes(namespace)
    yield low_peers(namespace)
    yield high_peers(namespace)
    yield container_memory_bytes(namespace)
    yield nim_gc_memory_bytes(namespace)
