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


# Mesh-health gauges, keyed by pod: `instance` is the podIP on k8s, not a node name.
def gossipsub_mesh_peers(namespace: str) -> MetricToScrape:
    return MetricToScrape(
        name="gossipsub_mesh_peers",
        query=f"sum by (pod) (libp2p_gossipsub_peers_per_topic_mesh{{namespace='{namespace}'}})",
        extract_field="pod",
        folder_name="mesh-peers/",
    )


def gossipsub_topic_peers(namespace: str) -> MetricToScrape:
    return MetricToScrape(
        name="gossipsub_topic_peers",
        query=f"sum by (pod) (libp2p_gossipsub_peers_per_topic_gossipsub{{namespace='{namespace}'}})",
        extract_field="pod",
        folder_name="topic-peers/",
    )


def connections(namespace: str) -> MetricToScrape:
    return MetricToScrape(
        name="connections",
        query=f"sum by (pod) (libp2p_peers{{namespace='{namespace}'}})",
        extract_field="pod",
        folder_name="connections/",
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
    yield gossipsub_mesh_peers(namespace)
    yield gossipsub_topic_peers(namespace)
    yield connections(namespace)


def _gossipsub_counter(namespace: str, name: str, metric: str, folder: str) -> MetricToScrape:
    # These pubsub/gossipsub counters carry a per-topic label; sum by pod to get one
    # monotonic series per node. The per-node total over the run is the last value.
    # `pod` is the pod name on both Shadow (the importer tags it) and the cluster (the
    # libp2p-nodes scrape relabels it), unlike `instance` which is the podIP on k8s.
    return MetricToScrape(
        name=name,
        query=f"sum by (pod) ({metric}{{namespace='{namespace}'}})",
        extract_field="pod",
        folder_name=folder,
    )


# Gossipsub control traffic (IHAVE/IWANT/GRAFT/PRUNE) and message efficiency counters.
# Reported off the Shadow runs, where the mesh and schedule are deterministic so these
# are exact (on the cluster they are too noisy to compare). Reduced per node by last
# value (total over the run); see gossipsub_summary.py.
_GOSSIPSUB_DETAIL = [
    ("gs_ihave_recv", "libp2p_pubsub_received_ihave_total", "gossipsub/ihave-recv/"),
    ("gs_iwant_sent", "libp2p_pubsub_broadcast_iwant_total", "gossipsub/iwant-sent/"),
    ("gs_iwant_recv", "libp2p_pubsub_received_iwant_total", "gossipsub/iwant-recv/"),
    ("gs_graft_sent", "libp2p_pubsub_broadcast_graft_total", "gossipsub/graft-sent/"),
    ("gs_graft_recv", "libp2p_pubsub_received_graft_total", "gossipsub/graft-recv/"),
    ("gs_prune_sent", "libp2p_pubsub_broadcast_prune_total", "gossipsub/prune-sent/"),
    ("gs_prune_recv", "libp2p_pubsub_received_prune_total", "gossipsub/prune-recv/"),
    ("gs_duplicate", "libp2p_gossipsub_duplicate_total", "gossipsub/duplicate/"),
    ("gs_received", "libp2p_gossipsub_received_total", "gossipsub/received/"),
    (
        "gs_idontwant_saved",
        "libp2p_gossipsub_idontwant_saved_messages_total",
        "gossipsub/idontwant-saved/",
    ),
]


def gossipsub_detail_metrics(namespace: str) -> Iterator[MetricToScrape]:
    for name, metric, folder in _GOSSIPSUB_DETAIL:
        yield _gossipsub_counter(namespace, name, metric, folder)
