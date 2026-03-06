import logging
from datetime import timedelta
from pathlib import Path
from typing import Literal

from core.base_bridge import BaseBridge, EventMapping
from libp2p.builders.helpers import LIBP2P_CONTAINER_NAME

logger = logging.getLogger(__name__)


class Bridge(BaseBridge):
    interval: Literal["complete", "stable"] = "complete"
    """Time interval for start and end times.

    complete: From the beginning to the end of the whole experiment run code

    stable: Just the time where nodes should have stablized.
    Calculated in _get_metadata_events by adding an offset from when message publishing starts and ends.
    """

    def get_metadata(self, events_log_path: str) -> dict:
        metadata = super().get_metadata(events_log_path)
        events = self._get_metadata_events(events_log_path)
        metadata["metadata"].update(events)
        metadata["stack"]["start_time"] = events[self.interval]["start"]
        metadata["stack"]["end_time"] = events[self.interval]["end"]
        metadata["stack"]["container_name"] = LIBP2P_CONTAINER_NAME
        return metadata

    def _get_metadata_events(self, events_log_path: str):
        events = [
            ("wait_for_clear_finished", Path("complete", "start"), timedelta(seconds=0)),
            ("internal_run_finished", Path("complete", "end"), timedelta(seconds=30)),
            ("start_messages", Path("stable", "start"), timedelta(minutes=3)),
            ("publisher_messages_finished", Path("stable", "end"), timedelta(seconds=-30)),
        ]
        events_list = list(
            map(
                lambda obj: EventMapping(key={"event": obj[0]}, target=obj[1], time_shift=obj[2]),
                events,
            )
        )
        return self._get_metadata_from_events_list(events_log_path, events_list)
