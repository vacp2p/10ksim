import json
from datetime import datetime

from src.deployments.core.event_log import find_events, parse_events_log


def write_events_log(tmp_path, events):
    log_path = tmp_path / "events.log"
    log_path.write_text("\n".join(json.dumps(event) for event in events) + "\n")
    return log_path


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


def test_find_events_matches_partial_event_keys(tmp_path):
    log_path = write_events_log(
        tmp_path,
        [
            {"event": "metadata", "experiment": "alpha", "extra": "keep"},
            {"event": "metadata", "experiment": "beta"},
        ],
    )

    assert find_events(log_path, {"event": "metadata", "experiment": "alpha"}) == [
        {"event": "metadata", "experiment": "alpha", "extra": "keep"}
    ]


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


def test_parse_events_log_ignores_events_missing_key_fields(tmp_path):
    log_path = write_events_log(
        tmp_path,
        [
            {"event": "start", "timestamp": "2026-01-01 12:00:00"},
            {"timestamp": "2026-01-01 12:01:00"},
        ],
    )

    metadata = parse_events_log(log_path, [({"event": "start"}, "stable.start")])

    assert metadata == {"stable": {"start": datetime(2026, 1, 1, 12, 0, 0)}}
