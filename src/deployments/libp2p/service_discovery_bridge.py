from typing import List, Literal

import src.deployments.core.event_window_bridge as event_window_bridge
from src.deployments.libp2p.builders.helpers import LIBP2P_CONTAINER_NAME


class ServiceDiscoveryBridge(event_window_bridge.EventWindowBridge):
    interval: Literal["complete", "discovery"] = "complete"
    container_name: str = LIBP2P_CONTAINER_NAME

    def event_windows(self) -> List[event_window_bridge.EventWindow]:
        return [
            event_window_bridge.EventWindow(
                key="complete",
                start=event_window_bridge.EventBound("wait_for_clear_finished"),
                end=event_window_bridge.EventBound("service_discovery_finished"),
            ),
            event_window_bridge.EventWindow(
                key="discovery",
                start=event_window_bridge.EventBound("service_discovery_started"),
                end=event_window_bridge.EventBound("service_discovery_finished"),
            ),
        ]
