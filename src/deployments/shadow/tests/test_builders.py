import io

import pytest
from ruamel.yaml import YAML

from src.deployments.shadow.builders import (
    build_configmap,
    build_pvc,
    build_shadow_job,
    render_publisher_config,
    render_shadow_yaml,
)


def _load_yaml(text: str):
    return YAML(typ="safe").load(io.StringIO(text))


# --------------------------------------------------------------------------- #
# render_publisher_config  (pod-api-requester batch config, reproduces traffic_sync)
# --------------------------------------------------------------------------- #
class TestRenderPublisherConfig:
    def test_hosts_expand_over_num_nodes(self):
        cfg = render_publisher_config(
            num_nodes=10, num_messages=5, msg_size_bytes=1000, delay_seconds=2.0
        )
        target = cfg["targets"][0]
        assert target["hosts"] == [f"pod-{i}" for i in range(10)]
        assert target["port"] == 8645
        # the host_template/host_count knobs were dropped in favour of an explicit list
        assert "host_template" not in target
        assert "host_count" not in target

    def test_action_reproduces_traffic_sync(self):
        cfg = render_publisher_config(
            num_nodes=10, num_messages=5, msg_size_bytes=1000, delay_seconds=2.0
        )
        action = cfg["actions"][0]
        assert action["pod_count"] == 5  # = num_messages
        assert action["delay"] == 2.0  # = delay_seconds
        assert action["order"] == "ascending"
        assert action["pod_start_index"] == 0
        assert action["loop_order"] == "foreach_request_target_each_pod"

    def test_publish_endpoint_payload(self):
        cfg = render_publisher_config(
            num_nodes=3, num_messages=2, msg_size_bytes=512, delay_seconds=1.0
        )
        endpoint = cfg["endpoints"][0]
        assert endpoint["url"] == "http://{node}:{port}/publish"
        assert endpoint["type"] == "POST"
        assert endpoint["paged"] is False
        assert endpoint["params"] == {"topic": "test", "msgSize": 512, "version": 1}

    def test_custom_port_and_topic(self):
        cfg = render_publisher_config(
            num_nodes=2, num_messages=1, msg_size_bytes=10, delay_seconds=0, port=9000, topic="foo"
        )
        assert cfg["targets"][0]["port"] == 9000
        assert cfg["endpoints"][0]["params"]["topic"] == "foo"

    def test_request_and_action_cross_references_resolve(self):
        cfg = render_publisher_config(
            num_nodes=2, num_messages=1, msg_size_bytes=10, delay_seconds=0
        )
        # the action references the request by name, the request references the endpoint
        assert cfg["requests"][0]["endpoint"] == cfg["endpoints"][0]["name"]
        assert cfg["actions"][0]["requests"] == [cfg["requests"][0]["name"]]
        assert cfg["actions"][0]["targets"] == [cfg["targets"][0]["name"]]


# --------------------------------------------------------------------------- #
# render_shadow_yaml  (peer hosts + publisher host)
# --------------------------------------------------------------------------- #
class TestRenderShadowYaml:
    def test_peer_hosts_plus_publisher(self):
        sy = render_shadow_yaml(num_nodes=4, sim_stop_time_s=180, publisher_start_s=90)
        hosts = sy["hosts"]
        assert sorted(h for h in hosts if h.startswith("pod-")) == [f"pod-{i}" for i in range(4)]
        assert "publisher" in hosts
        assert len(hosts) == 5  # 4 peers + 1 publisher

    def test_publisher_runs_requester_in_batch_mode(self):
        sy = render_shadow_yaml(num_nodes=4, sim_stop_time_s=180, publisher_start_s=90)
        proc = sy["hosts"]["publisher"]["processes"][0]
        assert proc["path"] == "/usr/bin/python3"
        assert (
            proc["args"] == "/app/api_requester.py --mode batch --config /sim/config/publisher.yaml"
        )
        assert proc["start_time"] == "90s"
        assert "traffic_sync" not in proc["args"]  # the swap removed the legacy injector

    def test_requester_app_path_override(self):
        sy = render_shadow_yaml(
            num_nodes=4, sim_stop_time_s=180, publisher_start_s=90, requester_app_path="/opt/req.py"
        )
        assert sy["hosts"]["publisher"]["processes"][0]["args"].startswith(
            "/opt/req.py --mode batch"
        )

    def test_peer_process_is_daemon_with_env(self):
        sy = render_shadow_yaml(
            num_nodes=3,
            sim_stop_time_s=120,
            publisher_start_s=60,
            connect_to=2,
            metrics_interval_s=15,
        )
        peer = sy["hosts"]["pod-0"]["processes"][0]
        assert peer["path"] == "./main"
        assert peer["start_time"] == "5000ms"
        assert peer["expected_final_state"] == "running"
        env = peer["environment"]
        assert env["PEERS"] == "3"
        assert env["CONNECTTO"] == "2"
        assert env["SHADOWENV"] == "true"
        assert env["METRICS_INTERVAL_S"] == "15"

    def test_general_and_network_section(self):
        sy = render_shadow_yaml(num_nodes=3, sim_stop_time_s=180, publisher_start_s=90)
        assert sy["general"]["stop_time"] == "180s"
        assert sy["general"]["progress"] is True
        assert sy["network"]["graph"]["type"] == "1_gbit_switch"

    def test_connect_to_must_be_less_than_num_nodes(self):
        with pytest.raises(ValueError):
            render_shadow_yaml(num_nodes=2, sim_stop_time_s=10, publisher_start_s=5, connect_to=2)


# --------------------------------------------------------------------------- #
# build_configmap  (ships shadow.yaml + publisher.yaml)
# --------------------------------------------------------------------------- #
class TestBuildConfigmap:
    def test_keys_metadata_and_yaml_roundtrip(self):
        sy = render_shadow_yaml(num_nodes=3, sim_stop_time_s=180, publisher_start_s=90)
        pub = render_publisher_config(
            num_nodes=3, num_messages=2, msg_size_bytes=1000, delay_seconds=2.0
        )
        cm = build_configmap(
            namespace="zerotesting-shadow", name="shadow-x", shadow_yaml=sy, publisher_config=pub
        )

        assert set(cm.data.keys()) == {"shadow.yaml", "publisher.yaml"}
        assert cm.metadata.name == "shadow-x"
        assert cm.metadata.namespace == "zerotesting-shadow"
        # the data values are valid YAML that round-trips back to the inputs
        assert _load_yaml(cm.data["publisher.yaml"])["targets"][0]["hosts"] == [
            f"pod-{i}" for i in range(3)
        ]
        assert "publisher" in _load_yaml(cm.data["shadow.yaml"])["hosts"]
        assert "traffic_sync.py" not in cm.data  # legacy injector no longer shipped


# --------------------------------------------------------------------------- #
# build_shadow_job / build_pvc  (k8s objects)
# --------------------------------------------------------------------------- #
class TestBuildShadowJob:
    def test_containers_images_and_ptrace(self):
        job = build_shadow_job(
            namespace="ns",
            name="job-x",
            configmap_name="cm",
            pvc_name="pvc",
            test_node_image="repo/test-node:tag",
            shadow_base_image="repo/base:tag",
        )
        spec = job.spec.template.spec
        assert [c.name for c in spec.init_containers] == ["fetch-test-node"]
        assert spec.init_containers[0].image == "repo/test-node:tag"
        assert spec.containers[0].name == "shadow"
        assert spec.containers[0].image == "repo/base:tag"
        # Shadow's syscall interposer needs SYS_PTRACE
        assert "SYS_PTRACE" in spec.containers[0].security_context.capabilities.add
        assert job.spec.backoff_limit == 0

    def test_node_pin_sets_node_selector(self):
        job = build_shadow_job(
            namespace="ns",
            name="job-x",
            configmap_name="cm",
            pvc_name="pvc",
            test_node_image="tn",
            shadow_base_image="base",
            node_pin="node-05",
        )
        assert job.spec.template.spec.node_selector == {"kubernetes.io/hostname": "node-05"}


class TestBuildPvc:
    def test_rwo_storage_and_class(self):
        pvc = build_pvc(namespace="ns", name="data", storage="7Gi", storage_class="longhorn")
        assert pvc.metadata.name == "data"
        assert pvc.spec.access_modes == ["ReadWriteOnce"]
        assert pvc.spec.storage_class_name == "longhorn"
        assert pvc.spec.resources.requests["storage"] == "7Gi"
