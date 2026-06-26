import json
from datetime import datetime, timedelta

import pytest
from kubernetes.client import V1Pod

from src.deployments.core.base_bridge import BaseBridge
from src.deployments.core.event_log import find_events, parse_events_log
from src.deployments.core.event_mapping import EventMapping
from src.deployments.core.k8s_types import V1Deployable
from src.deployments.core.metadata_times import (
    add_links,
    format_metadata_timestamps,
    format_timestamp_url,
    format_timestamp_vquery,
    get_valid_shifted_times,
)


def write_events_log(tmp_path, events):
    log_path = tmp_path / "events.log"
    log_path.write_text("\n".join(json.dumps(event) for event in events) + "\n")
    return log_path


def test_split_modules_expose_base_bridge_dependencies():
    assert BaseBridge
    assert EventMapping
    assert V1Deployable
    assert callable(add_links)
    assert callable(find_events)
    assert callable(format_metadata_timestamps)
    assert callable(format_timestamp_url)
    assert callable(format_timestamp_vquery)
    assert callable(get_valid_shifted_times)
    assert callable(parse_events_log)


def test_v1_deployable_alias_still_accepts_kubernetes_objects():
    pod = V1Pod()

    assert isinstance(pod, V1Deployable)


def test_find_events_accepts_string_and_path_log_paths(tmp_path):
    log_path = write_events_log(
        tmp_path,
        [
            {"event": "deployment", "phase": "start", "name": "alpha"},
            {"event": "deployment", "phase": "end", "name": "alpha"},
        ],
    )

    expected = [{"event": "deployment", "phase": "start", "name": "alpha"}]
    assert find_events(log_path, {"event": "deployment", "phase": "start"}) == expected
    assert find_events(str(log_path), {"event": "deployment", "phase": "start"}) == expected


def test_parse_events_log_accepts_string_paths_and_extracts_nested_metadata(tmp_path):
    log_path = write_events_log(
        tmp_path,
        [
            {"event": "start", "timestamp": "2026-01-01 12:00:00"},
            {"event": "params", "value": {"nodes": 10}},
        ],
    )

    def extract(event):
        if "value" in event:
            return event["value"]
        return datetime.strptime(event["timestamp"], "%Y-%m-%d %H:%M:%S")

    metadata = parse_events_log(
        str(log_path),
        [
            ({"event": "start"}, "stable.start"),
            ({"event": "params"}, "experiment.params"),
        ],
        extract=extract,
    )

    assert metadata == {
        "stable": {"start": datetime(2026, 1, 1, 12, 0, 0)},
        "experiment": {"params": {"nodes": 10}},
    }


def test_parse_events_log_default_extract_parses_timestamp(tmp_path):
    log_path = write_events_log(
        tmp_path,
        [{"event": "start", "timestamp": "2026-01-01 12:00:00"}],
    )

    metadata = parse_events_log(log_path, [({"event": "start"}, "stable.start")])

    assert metadata == {"stable": {"start": datetime(2026, 1, 1, 12, 0, 0)}}


def test_get_valid_shifted_times_applies_offsets_and_filters_invalid_ranges():
    metadata = {
        "stable": {"start": datetime(2026, 1, 1, 12, 0, 0), "end": datetime(2026, 1, 1, 12, 5, 0)},
        "invalid": {
            "start": datetime(2026, 1, 1, 12, 5, 0),
            "end": datetime(2026, 1, 1, 12, 0, 0),
        },
    }

    shifted = get_valid_shifted_times(
        {
            "stable.start": timedelta(minutes=1),
            "stable.end": timedelta(minutes=-1),
            "invalid.start": timedelta(minutes=0),
            "invalid.end": timedelta(minutes=0),
        },
        metadata,
    )

    assert shifted == {
        "stable": {"start": datetime(2026, 1, 1, 12, 1, 0), "end": datetime(2026, 1, 1, 12, 4, 0)}
    }


def test_format_metadata_timestamps_formats_nested_datetime_values():
    metadata = {"stable": {"start": datetime(2026, 1, 1, 12, 0, 0)}}

    assert format_metadata_timestamps(metadata, "vquery") == {
        "stable": {"start": "2026-01-01T12:00:00"}
    }
    assert format_metadata_timestamps(metadata, "url") == {
        "stable": {"start": "2026-01-01T12:00:00.000Z"}
    }


def test_format_metadata_timestamps_rejects_unknown_format():
    with pytest.raises(ValueError, match="Unknown format option"):
        format_metadata_timestamps({}, "unknown")


def test_add_links_formats_known_intervals_in_place():
    metadata = {"stable": {"start": "1000", "end": "2000"}, "other": {}}

    add_links(metadata, {"grafana": "https://example.test?from={start}&to={end}"})

    assert metadata["stable"]["grafana"] == "https://example.test?from=1000&to=2000"
    assert metadata["other"] == {}


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
