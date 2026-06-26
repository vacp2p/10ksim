import logging
from typing import Dict, Literal

from src.deployments.core.event_window_bridge import (
    EventWindowBridge,
    EventWindowEndpoint,
    event_window,
)
from src.deployments.libp2p.builders.helpers import LIBP2P_CONTAINER_NAME

logger = logging.getLogger(__name__)


class ServiceDiscoveryBridge(EventWindowBridge):
    interval: Literal["complete", "discovery"] = "complete"
    container_name: str = LIBP2P_CONTAINER_NAME
    event_windows: Dict[str, Dict[str, EventWindowEndpoint]] = {
        "complete": {
            "start": event_window("wait_for_clear_finished"),
            "end": event_window("service_discovery_finished"),
        },
        "discovery": {
            "start": event_window("service_discovery_started"),
            "end": event_window("service_discovery_finished"),
        },
    }
