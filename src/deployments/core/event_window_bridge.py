# Python Imports
import logging
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import List, Optional, Union

# Project Imports
from src.deployments.core.base_bridge import BaseBridge, EventMapping

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EventBound:
    key: dict
    time_shift: timedelta = timedelta(0)

    def __init__(self, event: Union[str, dict], time_shift: timedelta = timedelta(0)):
        key = {"event": event} if isinstance(event, str) else event
        object.__setattr__(self, "key", key)
        object.__setattr__(self, "time_shift", time_shift)


@dataclass(frozen=True)
class EventWindow:
    key: str
    start: EventBound
    end: EventBound


EventNotFound = "EventNotFound"


class EventWindowBridge(BaseBridge):
    interval: str = "complete"
    container_name: str

    def event_windows(self) -> List[EventWindow]:
        return []

    def get_metadata(self, events_log_path: Path) -> dict:
        metadata = super().get_metadata(events_log_path)
        namespace = metadata.get("metadata", {}).get("namespace")
        events = self._get_metadata_events(events_log_path, namespace=namespace)

        selected_interval = events.get(self.interval, {})
        start = selected_interval.get("start", EventNotFound)
        end = selected_interval.get("end", EventNotFound)

        if self.interval not in events:
            logger.warning(
                f"Analysis window `{self.interval}` not found. " f"Available: {list(events.keys())}"
            )
        elif start == EventNotFound or end == EventNotFound:
            logger.warning(
                f"Analysis window `{self.interval}` incomplete: " f"start={start}, end={end}"
            )

        metadata["stack"]["start_time"] = start
        metadata["stack"]["end_time"] = end
        metadata["results"] = events
        metadata["stack"]["container_name"] = self.container_name

        return metadata

    def _get_metadata_events(
        self, events_log_path: Path, *, namespace: Optional[str] = None
    ) -> dict:
        events_list = [
            EventMapping(
                key=bound.key,
                target=Path(window.key, bound_name),
                time_shift=bound.time_shift,
            )
            for window in self.event_windows()
            for bound_name, bound in (("start", window.start), ("end", window.end))
        ]
        return self._get_metadata_from_events_list(
            events_log_path, events_list, namespace=namespace
        )
