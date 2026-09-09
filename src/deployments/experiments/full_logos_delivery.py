import asyncio
import logging
from typing import Dict, Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat, NonNegativeInt

from src.deployments.core.configs.container import Image
from src.deployments.experiments.base_experiment import BaseExperiment, V1Deployable
from src.deployments.registry import experiment
from src.deployments.waku.bridge import Bridge
from src.deployments.waku.builders.builders import WakuStatefulSetBuilder

logger = logging.getLogger(__name__)

LogLevel = Literal["INFO", "DEBUG", "TRACE"]

BOOTSTRAP_SERVICE = "zerotesting-bootstrap"
FILTER_SERVER_SERVICE = "zerotesting-service"
LIGHTPUSH_SERVER_SERVICE = "zerotesting-lightpush-server"
FILTER_CLIENT_SERVICE = "zerotesting-filter"
LIGHTPUSH_CLIENT_SERVICE = "zerotesting-lightpush-client"


class ExpConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    num_bootstrap_nodes: NonNegativeInt = 5
    num_filter_servers: NonNegativeInt = 100
    num_lightpush_servers: NonNegativeInt = 100
    num_store_nodes: NonNegativeInt = 10
    num_filter_clients: NonNegativeInt = 500
    num_lightpush_clients: NonNegativeInt = 500
    num_messages: NonNegativeInt = 600
    msg_size_kbytes: NonNegativeInt = 1
    delay_cold_start: NonNegativeFloat = 300
    delay_after_publish: NonNegativeFloat = 1
    post_publish_dwell: NonNegativeFloat = 60
    log_level: LogLevel = "INFO"
    cmd_type: int = 1
    num_enrs: NonNegativeInt = 3
    image: Image = Field(
        default_factory=lambda: Image.from_str("soutullostatus/nwaku-jq-curl:v0.37.0-rc.4")
    )


def _base(name: str, namespace: str, num_nodes: NonNegativeInt) -> WakuStatefulSetBuilder:
    return WakuStatefulSetBuilder().with_waku_config(
        name=name, namespace=namespace, num_nodes=num_nodes
    )


def _finish(builder: WakuStatefulSetBuilder, config: ExpConfig) -> V1Deployable:
    """Applied last so it overrides whatever the role set."""
    builder.with_args({"--log-level": config.log_level}, on_duplicate="replace")
    builder.with_image(config.image)
    return builder.build()


def build_bootstrap(namespace: str, config: ExpConfig) -> V1Deployable:
    builder = (
        _base("bootstrap-0", namespace, config.num_bootstrap_nodes)
        .with_bootstrap(config.cmd_type)
        .with_env("SERVICE", BOOTSTRAP_SERVICE)
    )
    return _finish(builder, config)


def build_filter_servers(namespace: str, config: ExpConfig) -> V1Deployable:
    builder = (
        _base("fserver-0", namespace, config.num_filter_servers)
        .with_regression(config.cmd_type, config.num_enrs)
        .with_filter_server()
        .with_env("SERVICE", BOOTSTRAP_SERVICE)
    )
    return _finish(builder, config)


def build_lightpush_servers(namespace: str, config: ExpConfig) -> V1Deployable:
    builder = (
        _base("lpserver-0", namespace, config.num_lightpush_servers)
        .with_regression(config.cmd_type, config.num_enrs)
        .with_lightpush_server("zerotenkay-lightpush-server", LIGHTPUSH_SERVER_SERVICE)
        .with_env("SERVICE", BOOTSTRAP_SERVICE)
    )
    return _finish(builder, config)


def build_store_nodes(namespace: str, config: ExpConfig) -> V1Deployable:
    builder = (
        _base("store-0", namespace, config.num_store_nodes)
        .with_regression(config.cmd_type, config.num_enrs)
        .with_store()
        .with_env("SERVICE", BOOTSTRAP_SERVICE)
    )
    return _finish(builder, config)


def build_filter_clients(namespace: str, config: ExpConfig) -> V1Deployable:
    builder = (
        _base("fclient-0", namespace, config.num_filter_clients)
        .with_light_client(config.cmd_type, "zerotenkay-filter", FILTER_CLIENT_SERVICE)
        .with_filter_addrs(1, f"{FILTER_SERVER_SERVICE}.{namespace}")
    )
    return _finish(builder, config)


def build_lightpush_clients(namespace: str, config: ExpConfig) -> V1Deployable:
    builder = (
        _base("lpclient-0", namespace, config.num_lightpush_clients)
        .with_light_client(config.cmd_type, "zerotenkay-lightpush-client", LIGHTPUSH_CLIENT_SERVICE)
        .with_lightpush_addrs(1, f"{LIGHTPUSH_SERVER_SERVICE}.{namespace}")
    )
    return _finish(builder, config)


def build_nodes(namespace: str, config: ExpConfig) -> Dict[str, V1Deployable]:
    return {
        "bootstrap": build_bootstrap(namespace, config),
        "filter_server": build_filter_servers(namespace, config),
        "lightpush_server": build_lightpush_servers(namespace, config),
        "store": build_store_nodes(namespace, config),
        "filter_client": build_filter_clients(namespace, config),
        "lightpush_client": build_lightpush_clients(namespace, config),
    }


@experiment(name="full-logos-delivery")
class FullLogosDeliveryExperiment(BaseExperiment[ExpConfig]):
    """Relay, filter, lightpush and store nodes in one network."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_metadata(self) -> dict:
        return Bridge().get_metadata(self.events_log_path)

    def log_event(self, event):
        logger.info(event)
        return super().log_event(event)

    async def _run(self):
        self.log_event("run_start")

        deployments = build_nodes(self.namespace, self.config)

        # Clients resolve their service node address at init, so servers must be up first.
        await self.deploy(deployment=deployments["bootstrap"], wait_for_ready=True)
        for key in ("filter_server", "lightpush_server", "store"):
            await self.deploy(deployment=deployments[key], wait_for_ready=True)
        for key in ("filter_client", "lightpush_client"):
            await self.deploy(deployment=deployments[key], wait_for_ready=True)

        await asyncio.sleep(self.config.delay_cold_start)
        self.log_event("nodes_settled")

        await asyncio.sleep(self.config.post_publish_dwell)
        self.log_event("internal_run_finished")
