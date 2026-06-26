import json

from src.deployments.core.base_bridge import BaseBridge


def write_events_log(tmp_path, events):
    log_path = tmp_path / "events.log"
    log_path.write_text("\n".join(json.dumps(event) for event in events) + "\n")
    return log_path


def test_base_bridge_get_metadata_uses_extracted_event_log_helpers(tmp_path):
    log_path = write_events_log(
        tmp_path,
        [
            {
                "event": "deployment",
                "phase": "start",
                "kind": "StatefulSet",
                "name": "waku",
                "replicas": 3,
                "namespace": "test",
            },
            {
                "event": "metadata",
                "experiment_name": "demo",
                "experiment_class": "DemoExperiment",
                "command": "run",
                "kube_config": "kind",
            },
        ],
    )

    metadata = BaseBridge().get_metadata(log_path)

    assert metadata["stack"]["stateful_sets"] == ["waku"]
    assert metadata["stack"]["nodes_per_statefulset"] == [3]
    assert metadata["stack"]["namespace"] == "test"
    assert metadata["stack"]["name"] == "demo__waku_3"
    assert metadata["experiment"]["name"] == "demo"
    assert metadata["experiment"]["class"] == "DemoExperiment"
    assert metadata["metadata"]["command"] == "run"
    assert metadata["metadata"]["kube_config"] == "kind"
