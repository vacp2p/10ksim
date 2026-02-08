from typing import Iterator

from src.metrics.config import MetricToScrape


class Libp2pMetrics:
    @staticmethod
    def peers(namespace: str) -> MetricToScrape:
        return MetricToScrape(
            name="libp2p_peers",
            query="libp2p_peers",  # TODO: namespace
            extract_field="instance",
            folder_name="libp2p-peers/",
        )

    @staticmethod
    def open_streams(namespace: str) -> MetricToScrape:
        return MetricToScrape(
            name="libp2p_open_streams",
            query="libp2p_open_streams",  # TODO: namespace
            extract_field="instance-type-dir",
            folder_name="libp2p-open-streams/",
        )

    @staticmethod
    def network_in(namespace: str) -> MetricToScrape:
        return MetricToScrape(
            name="libp2p_network_in",
            query=f"rate(libp2p_network_bytes_total{{direction='in', namespace='{namespace}'}}[$__rate_interval])",
            extract_field="instance",
            folder_name="libp2p-in/",
        )

    @staticmethod
    def network_out(namespace: str) -> MetricToScrape:
        return MetricToScrape(
            name="libp2p_network_out",
            query=f"rate(libp2p_network_bytes_total{{direction='out', namespace='{namespace}'}}[$__rate_interval])",
            extract_field="instance",
            folder_name="libp2p-out/",
        )

    @staticmethod
    def container_recv_bytes(namespace: str) -> MetricToScrape:
        return MetricToScrape(
            name="container_recv_bytes",
            query=f"rate(container_network_receive_bytes_total{{namespace='{namespace}'}}[$__rate_interval])",
            extract_field="pod-node",
            folder_name="container-recv/",
        )

    @staticmethod
    def container_sent_bytes(namespace: str) -> MetricToScrape:
        return MetricToScrape(
            name="container_sent_bytes",
            query=f"rate(container_network_transmit_bytes_total{{namespace='{namespace}'}}[$__rate_interval])",
            extract_field="pod-node",
            folder_name="container-sent/",
        )

    @staticmethod
    def low_peers(namespace: str) -> MetricToScrape:
        return MetricToScrape(
            name="libp2p_low_peers",
            query="sum by(job) (libp2p_gossipsub_low_peers_topics)",  # TODO: namespace
            extract_field="job",
            folder_name="low-peers/",
        )

    @staticmethod
    def high_peers(namespace: str) -> MetricToScrape:
        return MetricToScrape(
            name="libp2p_high_peers",  # TODO: failing. libp2p_gossipsub_low_peers_topics exists but I don't see libp2p_gossipsub_healthy_peers_topics
            query="sum by(job) (libp2p_gossipsub_healthy_peers_topics)",  # TODO: namespace
            extract_field="job",
            folder_name="high-peers/",
        )

    @staticmethod
    def container_memory_bytes(namespace: str) -> MetricToScrape:
        return MetricToScrape(
            name="container_memory_bytes",
            query=f"sum by (pod) (container_memory_usage_bytes{{namespace='{namespace}'}})",
            extract_field="pod",
            folder_name="container-memory/",
        )

    @staticmethod
    def nim_gc_memory_bytes(namespace: str):
        # TODO: Not working. `nim_gc_mem_bytes` does not have `node` or `pod-node` keys.
        return MetricToScrape(
            name="nim_gc_memory_bytes",
            query=f"rate(nim_gc_mem_bytes{{namespace='{namespace}'}}[$__rate_interval])",
            extract_field="pod-node",
            folder_name="nim-gc-memory/",
        )


def libp2p_metrics(namespace: str) -> Iterator[MetricToScrape]:
    yield Libp2pMetrics.peers(namespace)
    yield Libp2pMetrics.open_streams(namespace)
    yield Libp2pMetrics.network_in(namespace)
    yield Libp2pMetrics.network_out(namespace)
    yield Libp2pMetrics.container_recv_bytes(namespace)
    yield Libp2pMetrics.container_sent_bytes(namespace)
    yield Libp2pMetrics.low_peers(namespace)
    yield Libp2pMetrics.high_peers(namespace)
    yield Libp2pMetrics.container_memory_bytes(namespace)
    yield Libp2pMetrics.nim_gc_memory_bytes(namespace)
