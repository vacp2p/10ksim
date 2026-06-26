import json
from datetime import timedelta
from pathlib import Path

from src.deployments.core.base_bridge import BaseBridge
from src.deployments.core.event_mapping import EventMapping


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


def test_base_bridge_preserves_full_metadata_flow_with_event_mappings(tmp_path):
    log_path = write_events_log(
        tmp_path,
        [
            {
                "event": "deployment",
                "phase": "start",
                "kind": "StatefulSet",
                "name": "waku-publisher",
                "replicas": 2,
                "namespace": "vaclab",
            },
            {
                "event": "deployment",
                "phase": "start",
                "kind": "StatefulSet",
                "name": "waku-subscriber",
                "replicas": 5,
                "namespace": "vaclab",
            },
            {
                "event": "metadata",
                "experiment_name": "waku-regression",
                "experiment_class": "WakuRegression",
                "command": "python deployment.py run",
                "kube_config": "vaclab",
                "args": {"message_rate": 10},
                "params": {"publisher_count": 2, "subscriber_count": 5},
            },
            {"event": "wait_for_clear_finished", "timestamp": "2026-01-01 12:00:00"},
            {"event": "publisher_deploy_start", "timestamp": "2026-01-01 12:03:00"},
            {"event": "publisher_wait_finished", "timestamp": "2026-01-01 12:15:00"},
            {"event": "internal_run_finished", "timestamp": "2026-01-01 12:20:00"},
        ],
    )
    bridge = BaseBridge()

    metadata = bridge.get_metadata(log_path)
    event_metadata = bridge._get_metadata_from_events_list(
        log_path,
        [
            EventMapping(
                key={"event": "wait_for_clear_finished"}, target=Path("complete") / "start"
            ),
            EventMapping(
                key={"event": "internal_run_finished"},
                target=Path("complete") / "end",
                time_shift=timedelta(seconds=30),
            ),
            EventMapping(
                key={"event": "publisher_deploy_start"},
                target=Path("stable") / "start",
                time_shift=timedelta(minutes=3),
            ),
            EventMapping(
                key={"event": "publisher_wait_finished"},
                target=Path("stable") / "end",
                time_shift=timedelta(seconds=-30),
            ),
        ],
    )
    metadata.update(event_metadata)

    assert metadata == {
        "stack": {
            "stateful_sets": ["waku-publisher", "waku-subscriber"],
            "nodes_per_statefulset": [2, 5],
            "namespace": "vaclab",
            "extra_fields": ["kubernetes.pod_name", "kubernetes.pod_node_name"],
            "name": "waku-regression__waku-publisher_2__waku-subscriber_5",
        },
        "experiment": {
            "name": "waku-regression",
            "class": "WakuRegression",
            "bridge_class": {
                "__type__": "src.deployments.core.base_bridge.BaseBridge",
                "statefulsets_key": "stateful_sets",
                "nodes_key": "nodes_per_statefulset",
            },
        },
        "metadata": {
            "command": "python deployment.py run",
            "kube_config": "vaclab",
            "namespace": "vaclab",
            "args": {"message_rate": 10},
        },
        "params": {"publisher_count": 2, "subscriber_count": 5},
        "complete": {"start": "2026-01-01T12:00:00", "end": "2026-01-01T12:20:30"},
        "stable": {"start": "2026-01-01T12:06:00", "end": "2026-01-01T12:14:30"},
    }
