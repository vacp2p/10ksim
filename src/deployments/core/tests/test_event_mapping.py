from datetime import timedelta
from pathlib import Path

from src.deployments.core.event_mapping import EventMapping


def test_event_mapping_defaults_time_shift_to_zero():
    mapping = EventMapping(key={"event": "start"}, target="stable.start")

    assert mapping.key == {"event": "start"}
    assert mapping.target == Path("stable.start")
    assert mapping.time_shift == timedelta(0)


def test_event_mapping_accepts_explicit_time_shift():
    mapping = EventMapping(
        key={"event": "end"},
        target=Path("stable.end"),
        time_shift=timedelta(seconds=-30),
    )

    assert mapping.target == Path("stable.end")
    assert mapping.time_shift == timedelta(seconds=-30)
