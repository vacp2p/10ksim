from result import Err, Ok

from dst_dashboard.config.data_structures import DataSourceConfig
from dst_dashboard.processors import vaclab_processor
from dst_dashboard.processors.vaclab_processor import (
    VaclabProcessor,
    _build_cpu,
    _build_instance_to_nodename,
    _build_memory,
    _build_network,
    _build_storage,
    _count_pods_per_node,
    _vector_to_dict,
    is_system_namespace,
)

# --------------------------------------------------------------------------- #
# Helper Functions
# --------------------------------------------------------------------------- #


def _vec(instance: str, value):
    """A single-series instant-query result vector keyed on `instance`."""
    return [{"metric": {"instance": instance}, "value": [1690000000, str(value)]}]


def _uname_vec(pairs):
    """pairs: list of (instance, nodename)."""
    return [{"metric": {"instance": i, "nodename": n}} for i, n in pairs]


def _pod_vec(entries):
    """entries: list of (node, namespace)."""
    return [{"metric": {"node": n, "namespace": ns}} for n, ns in entries]


NODE_01 = "node-01.ih-eu-mda1.misc.vaclab"
NODE_02 = "node-02.ih-eu-mda1.misc.vaclab"
METAL_01 = "metal-01.he-eu-hel1.misc.vacdst"


# --------------------------------------------------------------------------- #
# is_system_namespace
# --------------------------------------------------------------------------- #
class TestIsSystemNamespace:
    def test_exact_match_is_system(self):
        assert is_system_namespace("kube-system") is True

    def test_prefix_match_is_system(self):
        assert is_system_namespace("p-abc123") is True
        assert is_system_namespace("cattle-fleet-system") is True

    def test_workload_namespace_is_not_system(self):
        assert is_system_namespace("libp2p-lab") is False
        assert is_system_namespace("nimlibp2p") is False


# --------------------------------------------------------------------------- #
# _vector_to_dict
# --------------------------------------------------------------------------- #
class TestVectorToDict:
    def test_parses_values_by_label(self):
        vector = _vec(NODE_01, 42.5) + _vec(NODE_02, 7)
        assert _vector_to_dict(vector, "instance") == {NODE_01: 42.5, NODE_02: 7.0}

    def test_skips_series_missing_label_or_value(self):
        vector = [{"metric": {}, "value": [0, "1"]}, {"metric": {"instance": NODE_01}}]
        assert _vector_to_dict(vector, "instance") == {}


# --------------------------------------------------------------------------- #
# _build_instance_to_nodename
# --------------------------------------------------------------------------- #
class TestBuildInstanceToNodename:
    def test_discovers_every_reporting_node_including_non_vaclab(self):
        # Nodes are discovered live from whatever node_uname_info reports -
        # no suffix filtering, so the dashboard's own infra node shows up too.
        vector = _uname_vec(
            [
                ("10.0.0.1:9100", NODE_01),
                ("10.0.0.9:9100", METAL_01),
            ]
        )
        assert _build_instance_to_nodename(vector) == {
            "10.0.0.1:9100": NODE_01,
            "10.0.0.9:9100": METAL_01,
        }


# --------------------------------------------------------------------------- #
# _count_pods_per_node
# --------------------------------------------------------------------------- #
class TestCountPodsPerNode:
    def test_excludes_system_namespaces_but_counts_any_node(self):
        vector = _pod_vec(
            [
                (NODE_01, "libp2p-lab"),
                (NODE_01, "kube-system"),
                (NODE_01, "p-abc123"),
                (NODE_02, "nimlibp2p"),
                (METAL_01, "default"),
                (METAL_01, "dst-dashboard"),
            ]
        )
        assert _count_pods_per_node(vector) == {NODE_01: 1, NODE_02: 1, METAL_01: 1}

    def test_node_with_only_system_pods_is_absent_not_zeroed(self):
        # Callers default to 0 via .get(hostname, 0); the counter itself just
        # never mentions a node with no countable pods.
        vector = _pod_vec([(NODE_01, "kube-system")])
        assert _count_pods_per_node(vector) == {}


# --------------------------------------------------------------------------- #
# _build_cpu / _build_memory / _build_storage / _build_network
# --------------------------------------------------------------------------- #
class TestBuildMetricBlocks:
    def test_build_cpu_computes_used_from_idle_fraction(self):
        result = _build_cpu(NODE_01, {NODE_01: 128.0}, {NODE_01: 0.9})
        assert result == {"used_cores": 12.8, "capacity_cores": 128.0, "used_percent": 10.0}

    def test_build_cpu_returns_none_when_metric_missing(self):
        # This metric type failed cluster-wide for this instance - should
        # degrade to None, not crash or fabricate a value.
        assert _build_cpu(NODE_01, {}, {NODE_01: 0.9}) is None

    def test_build_memory_computes_used_from_available(self):
        result = _build_memory(NODE_01, {NODE_01: 1000.0}, {NODE_01: 750.0})
        assert result == {"used_bytes": 250, "capacity_bytes": 1000, "used_percent": 25.0}

    def test_build_storage_computes_used_from_available(self):
        result = _build_storage(NODE_01, {NODE_01: 500.0}, {NODE_01: 100.0})
        assert result == {"used_bytes": 400, "capacity_bytes": 500, "used_percent": 80.0}

    def test_build_network_sums_rx_and_tx_against_capacity(self):
        result = _build_network(NODE_01, {NODE_01: 30.0}, {NODE_01: 20.0}, {NODE_01: 500.0})
        assert result == {
            "rx_bytes_per_sec": 30.0,
            "tx_bytes_per_sec": 20.0,
            "used_bytes_per_sec": 50.0,
            "capacity_bytes_per_sec": 500.0,
            "used_percent": 10.0,
        }

    def test_build_network_used_percent_none_when_capacity_missing(self):
        result = _build_network(NODE_01, {NODE_01: 30.0}, {NODE_01: 20.0}, {})
        assert result["used_percent"] is None


# --------------------------------------------------------------------------- #
# VaclabProcessor.get_snapshot
# --------------------------------------------------------------------------- #
class TestVaclabProcessorSnapshot:
    def _patch_queries(self, monkeypatch, overrides=None):
        """Fake query_instant that dispatches on the PromQL text, so
        get_snapshot's real query dict/keys are exercised end to end."""
        overrides = overrides or {}

        def fake_query_instant(base_url, expr, timeout=10):
            if "node_uname_info" in expr:
                key = "uname"
            elif "count(node_cpu_seconds_total" in expr:
                key = "cpu_capacity"
            elif "node_cpu_seconds_total" in expr:
                key = "cpu_idle_fraction"
            elif "MemTotal" in expr:
                key = "mem_total"
            elif "MemAvailable" in expr:
                key = "mem_available"
            elif "node_network_receive_bytes_total" in expr:
                key = "net_rx"
            elif "node_network_transmit_bytes_total" in expr:
                key = "net_tx"
            elif "node_network_speed_bytes" in expr:
                key = "net_capacity"
            elif "kube_pod_info" in expr:
                key = "pods"
            elif "node_filesystem_size_bytes" in expr:
                key = "fs_size"
            elif "node_filesystem_avail_bytes" in expr:
                key = "fs_avail"
            else:
                raise AssertionError(f"Unexpected query: {expr}")

            if key in overrides:
                return overrides[key]
            return Err("no fixture for this metric")

        monkeypatch.setattr(vaclab_processor, "query_instant", fake_query_instant)

    def test_snapshot_is_empty_when_no_nodes_report(self, monkeypatch):
        self._patch_queries(monkeypatch)
        processor = VaclabProcessor(DataSourceConfig(name="victoria-metrics", type="Prometheus", url="http://x/"))
        snapshot = processor.get_snapshot()
        assert snapshot["nodes"] == []

    def test_snapshot_discovers_nodes_dynamically_including_non_vaclab(self, monkeypatch):
        overrides = {
            "uname": Ok(_uname_vec([("10.0.0.1:9100", NODE_01), ("10.0.0.9:9100", METAL_01)])),
            "cpu_capacity": Ok(_vec("10.0.0.1:9100", 128) + _vec("10.0.0.9:9100", 64)),
            "cpu_idle_fraction": Ok(_vec("10.0.0.1:9100", 0.9) + _vec("10.0.0.9:9100", 0.5)),
            "mem_total": Ok(_vec("10.0.0.1:9100", 1000) + _vec("10.0.0.9:9100", 2000)),
            "mem_available": Ok(_vec("10.0.0.1:9100", 750) + _vec("10.0.0.9:9100", 1000)),
            "net_rx": Ok(_vec("10.0.0.1:9100", 30) + _vec("10.0.0.9:9100", 10)),
            "net_tx": Ok(_vec("10.0.0.1:9100", 20) + _vec("10.0.0.9:9100", 10)),
            "net_capacity": Ok(_vec("10.0.0.1:9100", 500) + _vec("10.0.0.9:9100", 500)),
            "fs_size": Ok(_vec("10.0.0.1:9100", 500) + _vec("10.0.0.9:9100", 500)),
            "fs_avail": Ok(_vec("10.0.0.1:9100", 100) + _vec("10.0.0.9:9100", 100)),
            "pods": Ok(
                _pod_vec(
                    [(NODE_01, "libp2p-lab"), (NODE_01, "kube-system"), (METAL_01, "default")]
                )
            ),
        }
        self._patch_queries(monkeypatch, overrides)
        processor = VaclabProcessor(DataSourceConfig(name="victoria-metrics", type="Prometheus", url="http://x/"))
        snapshot = processor.get_snapshot()

        hostnames = [n["hostname"] for n in snapshot["nodes"]]
        assert set(hostnames) == {NODE_01, METAL_01}
        assert "role" not in snapshot["nodes"][0]
        assert "reachable" not in snapshot["nodes"][0]

        node_01 = next(n for n in snapshot["nodes"] if n["hostname"] == NODE_01)
        assert node_01["cpu"]["used_percent"] == 10.0
        assert node_01["memory"]["used_percent"] == 25.0
        assert node_01["pod_count"] == 1  # kube-system pod excluded

        metal_01 = next(n for n in snapshot["nodes"] if n["hostname"] == METAL_01)
        assert metal_01["pod_count"] == 1

    def test_node_present_in_uname_but_missing_other_metrics_gets_null_blocks(self, monkeypatch):
        overrides = {"uname": Ok(_uname_vec([("10.0.0.2:9100", NODE_02)]))}
        self._patch_queries(monkeypatch, overrides)
        processor = VaclabProcessor(DataSourceConfig(name="victoria-metrics", type="Prometheus", url="http://x/"))
        snapshot = processor.get_snapshot()

        node_02 = next(n for n in snapshot["nodes"] if n["hostname"] == NODE_02)
        assert node_02["cpu"] is None
        assert node_02["memory"] is None
        assert node_02["storage"] is None
        assert node_02["network"] is None
        assert node_02["pod_count"] == 0
