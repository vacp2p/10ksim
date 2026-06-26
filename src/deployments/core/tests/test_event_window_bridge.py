# Python Import
import json
from datetime import timedelta
from typing import Dict

import pytest

# Project Import
from src.deployments.core.event_window_bridge import (
    EventWindowBridge,
    EventWindowEndpoint,
    event_window,
)
from src.deployments.libp2p.bridge import Bridge as Libp2pBridge
from src.deployments.libp2p.builders.helpers import LIBP2P_CONTAINER_NAME
from src.deployments.waku.bridge import Bridge as WakuBridge
from src.deployments.waku.builders.helpers import WAKU_CONTAINER_NAME


def write_events_log(tmp_path, events):
    log_path = tmp_path / "events.log"
    log_path.write_text("\n".join(json.dumps(event) for event in events) + "\n")
    return log_path


class ExampleWindowBridge(EventWindowBridge):
    interval: str = "stable"
    container_name: str = "example-container"
    event_windows: Dict[str, Dict[str, EventWindowEndpoint]] = {
        "complete": {
            "start": event_window("experiment_started"),
            "end": event_window("experiment_finished", timedelta(seconds=30)),
        },
        "stable": {
            "start": event_window(
                {"event": "messages_started", "role": "publisher"}, timedelta(minutes=3)
            ),
            "end": event_window("messages_finished", timedelta(seconds=-30)),
        },
    }


def test_event_window_builds_endpoint_from_string_event():
    endpoint = event_window("experiment_started", timedelta(seconds=5))

    assert endpoint == EventWindowEndpoint(
        key={"event": "experiment_started"}, time_shift=timedelta(seconds=5)
    )


def test_event_window_builds_endpoint_from_dict_event():
    endpoint = event_window({"event": "messages_started", "role": "publisher"})

    assert endpoint == EventWindowEndpoint(
        key={"event": "messages_started", "role": "publisher"},
        time_shift=timedelta(0),
    )


def test_event_window_bridge_extracts_results_and_selected_interval(tmp_path):
    log_path = write_events_log(
        tmp_path,
        [
            {
                "event": "deployment",
                "phase": "start",
                "kind": "StatefulSet",
                "name": "publisher",
                "replicas": 2,
                "namespace": "test",
            },
            {
                "event": "metadata",
                "experiment_name": "window-demo",
                "experiment_class": "WindowDemo",
                "command": "run",
                "kube_config": "kind",
            },
            {"event": "experiment_started", "timestamp": "2026-01-01 12:00:00"},
            {"event": "experiment_finished", "timestamp": "2026-01-01 12:30:00"},
            {
                "event": "messages_started",
                "role": "publisher",
                "timestamp": "2026-01-01 12:05:00",
            },
            {"event": "messages_finished", "timestamp": "2026-01-01 12:20:00"},
        ],
    )

    metadata = ExampleWindowBridge().get_metadata(log_path)

    assert metadata["results"] == {
        "complete": {"start": "2026-01-01T12:00:00", "end": "2026-01-01T12:30:30"},
        "stable": {"start": "2026-01-01T12:08:00", "end": "2026-01-01T12:19:30"},
    }
    assert metadata["stack"]["start_time"] == "2026-01-01T12:08:00"
    assert metadata["stack"]["end_time"] == "2026-01-01T12:19:30"
    assert metadata["stack"]["container_name"] == "example-container"
    assert metadata["stack"]["stateful_sets"] == ["publisher"]
    assert metadata["experiment"]["name"] == "window-demo"


def test_event_window_bridge_raises_when_selected_interval_is_missing(tmp_path):
    log_path = write_events_log(
        tmp_path,
        [
            {
                "event": "deployment",
                "phase": "start",
                "kind": "StatefulSet",
                "name": "publisher",
                "replicas": 2,
                "namespace": "test",
            },
            {
                "event": "metadata",
                "experiment_name": "window-demo",
                "experiment_class": "WindowDemo",
            },
            {"event": "experiment_started", "timestamp": "2026-01-01 12:00:00"},
            {"event": "experiment_finished", "timestamp": "2026-01-01 12:30:00"},
        ],
    )

    with pytest.raises(ValueError, match="Missing `stable` analysis window"):
        ExampleWindowBridge().get_metadata(log_path)


@pytest.mark.parametrize(
    ("bridge_cls", "container_name"),
    [
        (Libp2pBridge, LIBP2P_CONTAINER_NAME),
        (WakuBridge, WAKU_CONTAINER_NAME),
    ],
)
def test_protocol_bridges_define_complete_and_stable_event_windows(bridge_cls, container_name):
    bridge = bridge_cls()

    assert bridge.interval == "complete"
    assert bridge.container_name == container_name
    assert bridge.event_windows == {
        "complete": {
            "start": EventWindowEndpoint(
                key={"event": "wait_for_clear_finished"}, time_shift=timedelta(0)
            ),
            "end": EventWindowEndpoint(
                key={"event": "internal_run_finished"}, time_shift=timedelta(seconds=30)
            ),
        },
        "stable": {
            "start": EventWindowEndpoint(
                key={"event": "start_messages"}, time_shift=timedelta(minutes=3)
            ),
            "end": EventWindowEndpoint(
                key={"event": "publisher_messages_finished"},
                time_shift=timedelta(seconds=-30),
            ),
        },
    }
