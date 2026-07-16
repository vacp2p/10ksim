import asyncio
import logging
import random
import traceback
from typing import Literal

from kubernetes.client import V1Probe, V1ServicePort, V1StatefulSet, V1TCPSocketAction
from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt, model_validator

from src.deployments.core.builders import ServiceBuilder
from src.deployments.core.configs.container import Image
from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.libp2p.bridge import Bridge
from src.deployments.libp2p.builders.builders import Libp2pStatefulSetBuilder
from src.deployments.libp2p.builders.builders import Option as NimLibp2p
from src.deployments.libp2p.builders.helpers import readiness_probe_metrics
from src.deployments.pod_api_requester.builder import PodApiRequesterBuilder
from src.deployments.pod_api_requester.configs import Target
from src.deployments.pod_api_requester.nimlibp2p import libp2p_dst_node_publish
from src.deployments.pod_api_requester.pod_api_requester import PodApiApplicationError, PodApiError
from src.deployments.registry import experiment

logger = logging.getLogger(__name__)

Muxer = Literal["yamux", "quic", "mplex"]
Discovery = Literal["static", "kad-dht"]

BOOTSTRAP_NAME = "bootstrap"


class ExpConfig(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    num_relay_nodes: NonNegativeInt = 30
    num_messages: NonNegativeInt = 20
    message_size_bytes: NonNegativeInt = 1000
    delay_cold_start: NonNegativeFloat = 60
    delay_after_publish: NonNegativeFloat = 1
    muxer: Muxer = "yamux"
    image: Image = Image(repo="pearsonwhite/dst-nimlibp2p-logging", tag="wip-4.2-1.16.0-amd")
    discovery: Discovery = "static"
    """ "kad-dht" discovers peers through a bootstrap node; "static" uses the CONNECTTO dial."""
    connect_to: NonNegativeInt = 10
    """Number of nodes to try to connect to for each node when starting up"""
    bootstrap_nodes: NonNegativeInt = 1
    network_delay: NonNegativeInt = 0
    network_jitter: NonNegativeInt = 0
    node_start_delay: NonNegativeInt = 60
    wait_nodes_ready: bool = True

    @model_validator(mode="after")
    def _check_bootstrap_nodes(self):
        if self.discovery == "kad-dht" and self.bootstrap_nodes < 1:
            raise ValueError("kad-dht discovery requires bootstrap_nodes >= 1")
        return self


def bootstrap_dns(namespace: str) -> str:
    return f"{BOOTSTRAP_NAME}.{namespace}.svc.cluster.local"


def build_nodes(
    namespace: str,
    params: ExpConfig,
) -> V1StatefulSet:
    builder = (
        Libp2pStatefulSetBuilder()
        .with_libp2p_config(
            name="pod",
            namespace=namespace,
            num_nodes=params.num_relay_nodes,
            dns_searches=["nimp2p-service"],
        )
        .with_option(NimLibp2p.peers, params.num_relay_nodes)
        .with_option(NimLibp2p.self_trigger, True)
        .with_option(NimLibp2p.muxer, params.muxer)
        .with_option(NimLibp2p.cold_start_delay, params.node_start_delay)
        .with_readiness_probe(readiness_probe_metrics())
        .with_image(params.image)
    )
    if params.discovery == "kad-dht":
        builder = (
            builder.with_option(NimLibp2p.node_role, "RoleNormal")
            .with_option(NimLibp2p.discovery, "kad-dht")
            .with_option(NimLibp2p.service, bootstrap_dns(namespace))
        )
    else:
        builder = builder.with_option(NimLibp2p.service, "nimp2p-service").with_option(
            NimLibp2p.connect_to, params.connect_to
        )
    if params.network_delay or params.network_jitter:
        builder = builder.with_network_delay(
            delay=params.network_delay, jitter=params.network_jitter
        )

    return builder.build()


def build_bootstrap_service(namespace: str):
    return (
        ServiceBuilder()
        .with_name(BOOTSTRAP_NAME)
        .with_namespace(namespace)
        .with_cluster_ip("None")
        .with_selector("app", "zerotenkay")
        .with_selector("role", "bootstrap")
        .with_port(V1ServicePort(name="p2p", port=5000, target_port=5000))
        .build()
    )


def build_static_service(namespace: str):
    # Headless DNS for the static dial; publish_not_ready_addresses lets nodes
    # resolve each other before any is ready, else the mesh can't bootstrap.
    return (
        ServiceBuilder()
        .with_name("nimp2p-service")
        .with_namespace(namespace)
        .with_cluster_ip("None")
        .with_publish_not_ready_addresses(True)
        .with_selector("app", "zerotenkay")
        .with_port(V1ServicePort(name="p2p-quic", port=5000, target_port=5000, protocol="UDP"))
        .with_port(V1ServicePort(name="p2p-tcp", port=5000, target_port=5000, protocol="TCP"))
        .with_port(V1ServicePort(name="metrics", port=8008, target_port=8008, protocol="TCP"))
        .with_port(V1ServicePort(name="publish", port=8645, target_port=8645, protocol="TCP"))
        .build()
    )


def build_bootstrap_nodes(namespace: str, params: ExpConfig) -> V1StatefulSet:
    # Every node holds a link to the anchor, so it must accept more than num_relay_nodes.
    # Probe the metrics port (always TCP, unlike the p2p port under quic).
    return (
        Libp2pStatefulSetBuilder()
        .with_libp2p_config(
            name=BOOTSTRAP_NAME, namespace=namespace, num_nodes=params.bootstrap_nodes
        )
        .with_label("role", "bootstrap")
        .with_option(NimLibp2p.node_role, "RoleBootstrap")
        .with_option(NimLibp2p.discovery, "kad-dht")
        .with_option(NimLibp2p.muxer, params.muxer)
        .with_option(NimLibp2p.max_connections, params.num_relay_nodes + 100)
        .with_readiness_probe(
            V1Probe(
                tcp_socket=V1TCPSocketAction(port=8008),
                initial_delay_seconds=5,
                period_seconds=2,
                failure_threshold=3,
            )
        )
        .with_image(params.image)
        .build()
    )


async def publish(config, namespace, random_name):
    try:
        target = Target(
            name="libp2p-node",
            name_template=random_name,
            service="nimp2p-service",
            port=8645,
        )
        await libp2p_dst_node_publish(
            namespace=namespace, target=target, msg_size_bytes=config.message_size_bytes
        )
    except PodApiApplicationError as e:
        logger.error(f"PodApiApplicationError: {e} {traceback.format_exc()}")
    except PodApiError as e:
        logger.error(f"PodApiError: {e} {traceback.format_exc()}")
    except Exception as e:
        logger.error(f"Other exception: {e} {traceback.format_exc()}")


@experiment(name="nimlibp2p")
class NimLibp2pExperiment(BaseExperiment[ExpConfig]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_metadata(self) -> dict:
        return Bridge().get_metadata(self.events_log_path)

    async def _run(self):
        self.log_event("run_start")

        # Publisher
        publisher = (
            PodApiRequesterBuilder().with_namespace(self.namespace).with_mode("server").build()
        )
        await self.deploy(deployment=publisher, wait_for_ready=True)

        # Bootstrap (kad-dht only): anchor node + headless discovery service. Deployed
        # before the nodes so the mesh can form through it once the nodes wake up.
        if self.config.discovery == "kad-dht":
            bootstrap_service = build_bootstrap_service(self.namespace)
            self.dump_yaml(bootstrap_service, "bootstrap-service")
            await self.deploy(deployment=bootstrap_service)

            bootstrap = build_bootstrap_nodes(namespace=self.namespace, params=self.config)
            self.dump_yaml(bootstrap, "bootstrap")
            await self.deploy(deployment=bootstrap, wait_for_ready=True)
        else:
            # Static discovery resolves peers via this service, so deploy it first.
            static_service = build_static_service(self.namespace)
            self.dump_yaml(static_service, "static-service")
            await self.deploy(deployment=static_service, exist_ok=True)

        # Nodes
        nodes = build_nodes(
            namespace=self.namespace,
            params=self.config,
        )
        name = nodes.metadata.name
        namespace = nodes.metadata.namespace

        await self.deploy(deployment=nodes, wait_for_ready=self.config.wait_nodes_ready)

        await asyncio.sleep(self.config.delay_cold_start)

        logger.info(f"Starting publish loop for nodes in `{name}`")

        self.log_event("start_messages")

        tasks = []
        for msg_index in range(self.config.num_messages):
            index = random.randint(0, self.config.num_relay_nodes - 1)
            random_name = f"{name}-{index}"
            self.log_event({"event": "publish", "node": random_name, "index": msg_index})
            tasks.append(asyncio.create_task(publish(self.config, namespace, random_name)))
            await asyncio.sleep(self.config.delay_after_publish)
        await asyncio.gather(*tasks)

        self.log_event("publisher_messages_finished")

        await asyncio.sleep(20)
        self.log_event("publisher_wait_finished")

        self.log_event("internal_run_finished")
