# Python Imports
import logging
from datetime import timedelta
from typing import Dict, Literal

# Project Imports
from src.deployments.core.event_window_bridge import (
    EventWindowBridge,
    EventWindowEndpoint,
    event_window,
)
from src.deployments.libp2p.builders.helpers import LIBP2P_CONTAINER_NAME

logger = logging.getLogger(__name__)


class Bridge(EventWindowBridge):
    interval: Literal["complete", "stable"] = "complete"
    """Time interval for start and end times.

    complete: From the beginning to the end of the whole experiment run code

    stable: Just the time where nodes should have stablized.
    Calculated by adding offsets to message publishing start/end events.
    """

    container_name: str = LIBP2P_CONTAINER_NAME
    event_windows: Dict[str, Dict[str, EventWindowEndpoint]] = {
        "complete": {
            "start": event_window("wait_for_clear_finished"),
            "end": event_window("internal_run_finished", timedelta(seconds=30)),
        },
        "stable": {
            "start": event_window("start_messages", timedelta(minutes=3)),
            "end": event_window("publisher_messages_finished", timedelta(seconds=-30)),
        },
    }
