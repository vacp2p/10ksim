# Python Imports
import logging
from datetime import timedelta
from typing import List, Literal

# Project Imports
import src.deployments.core.event_window_bridge as event_window_bridge
from src.deployments.libp2p.builders.helpers import LIBP2P_CONTAINER_NAME

logger = logging.getLogger(__name__)


class Bridge(event_window_bridge.EventWindowBridge):
    interval: Literal["complete", "stable"] = "complete"
    """Time interval for start and end times.

    complete: From the beginning to the end of the whole experiment run code

    stable: Just the time where nodes should have stablized.
    Calculated by adding offsets to message publishing start/end events.
    """

    container_name: str = LIBP2P_CONTAINER_NAME

    def event_windows(self) -> List[event_window_bridge.EventWindow]:
        return [
            event_window_bridge.EventWindow(
                key="complete",
                start=event_window_bridge.EventBound("wait_for_clear_finished"),
                end=event_window_bridge.EventBound("internal_run_finished", timedelta(seconds=30)),
            ),
            event_window_bridge.EventWindow(
                key="stable",
                start=event_window_bridge.EventBound("start_messages", timedelta(minutes=3)),
                end=event_window_bridge.EventBound(
                    "publisher_messages_finished", timedelta(seconds=-30)
                ),
            ),
        ]
