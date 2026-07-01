# Python Imports
from datetime import timedelta
from pathlib import Path
from typing import Dict, Literal, Union

from pydantic import BaseModel, Field

# Project Imports
from src.deployments.core.base_bridge import BaseBridge, EventMapping

EventBound = Literal["start", "end"]


class EventWindowEndpoint(BaseModel):
    key: dict
    time_shift: timedelta = Field(default_factory=lambda: timedelta(0))


def event_window(
    event: Union[str, dict], time_shift: timedelta = timedelta(0)
) -> EventWindowEndpoint:
    key = {"event": event} if isinstance(event, str) else event
    return EventWindowEndpoint(key=key, time_shift=time_shift)


class EventWindowBridge(BaseBridge):
    interval: str = "complete"
    container_name: str
    event_windows: Dict[str, Dict[EventBound, EventWindowEndpoint]] = Field(default_factory=dict)

    def get_metadata(self, events_log_path: Path) -> dict:
        metadata = super().get_metadata(events_log_path)
        events = self._get_metadata_events(events_log_path)

        try:
            selected_interval = events[self.interval]
            metadata["stack"]["start_time"] = selected_interval["start"]
            metadata["stack"]["end_time"] = selected_interval["end"]
        except KeyError as e:
            raise ValueError(
                f"Missing `{self.interval}` analysis window in events metadata. "
                f"interval: `{self.interval}` events: `{events}`"
            ) from e

        metadata["results"] = events
        metadata["stack"]["container_name"] = self.container_name

        return metadata

    def _get_metadata_events(self, events_log_path: Path) -> dict:
        events_list = [
            EventMapping(
                key=endpoint.key,
                target=Path(window_name, bound),
                time_shift=endpoint.time_shift,
            )
            for window_name, bounds in self.event_windows.items()
            for bound, endpoint in bounds.items()
        ]
        return self._get_metadata_from_events_list(events_log_path, events_list)
