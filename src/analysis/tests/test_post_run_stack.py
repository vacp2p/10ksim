import pytest

from src.analysis.utils.stack import stack_for_window


def test_stack_for_window_returns_stack_copy_with_selected_window():
    metadata = {
        "stack": {
            "namespace": "nimlibp2p",
            "container_name": "pod-0",
            "start_time": "complete-start",
            "end_time": "complete-end",
        },
        "results": {
            "complete": {"start": "complete-start", "end": "complete-end"},
            "discovery": {"start": "discovery-start", "end": "discovery-end"},
        },
    }

    stack = stack_for_window(metadata, "discovery")

    assert stack == {
        "namespace": "nimlibp2p",
        "container_name": "pod-0",
        "start_time": "discovery-start",
        "end_time": "discovery-end",
    }


def test_stack_for_window_does_not_mutate_metadata_stack():
    metadata = {
        "stack": {"start_time": "complete-start", "end_time": "complete-end"},
        "results": {"discovery": {"start": "discovery-start", "end": "discovery-end"}},
    }

    stack = stack_for_window(metadata, "discovery")

    assert stack is not metadata["stack"]
    assert metadata["stack"] == {"start_time": "complete-start", "end_time": "complete-end"}


def test_stack_for_window_rejects_missing_window():
    metadata = {
        "stack": {},
        "results": {"complete": {"start": "complete-start", "end": "complete-end"}},
    }

    with pytest.raises(ValueError, match="missing results window `discovery`"):
        stack_for_window(metadata, "discovery")


def test_stack_for_window_rejects_window_without_start_or_end():
    metadata = {
        "stack": {},
        "results": {"discovery": {"start": "discovery-start"}},
    }

    with pytest.raises(ValueError, match="missing keys: \\['end'\\]"):
        stack_for_window(metadata, "discovery")
