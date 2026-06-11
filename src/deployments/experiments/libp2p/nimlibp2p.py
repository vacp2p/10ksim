import asyncio
import logging
import random
import traceback
from typing import Literal

from kubernetes.client import V1StatefulSet
from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

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


class ExpConfig(BaseModel):
    num_nodes: NonNegativeInt = 1000
    num_messages: NonNegativeInt = 600
    message_size_bytes: NonNegativeInt = 1000
    delay_cold_start: NonNegativeFloat = 60
    delay_after_publish: NonNegativeFloat = 1
    muxer: Muxer = "yamux"
    image: Image = Image(repo="soutullostatus/nimlibp2p", tag="v2.0.0")
    connect_to: NonNegativeInt = 10
    network_delay: NonNegativeInt = 0
    network_jitter: NonNegativeInt = 0
    start_sleep: NonNegativeInt = 180


def build_nodes(
    namespace: str,
    params: ExpConfig,
) -> V1StatefulSet:
    builder = (
        Libp2pStatefulSetBuilder()
        .with_libp2p_config(
            name="pod",
            namespace=namespace,
            num_nodes=params.num_nodes,
            dns_searches=["nimp2p-service"],
        )
        .with_option(NimLibp2p.peers, params.num_nodes)
        .with_option(NimLibp2p.self_trigger, True)
        .with_option(NimLibp2p.service, "nimp2p-service")
        .with_option(NimLibp2p.muxer, params.muxer)
        .with_option(NimLibp2p.connect_to, params.connect_to)
        .with_option(NimLibp2p.start_sleep, params.start_sleep)
        .with_readiness_probe(readiness_probe_metrics())
        .with_pull_policy("IfNotPresent")
        .with_image(params.image)
    )
    if params.network_delay or params.network_jitter:
        builder = builder.with_network_delay(
            delay=params.network_delay, jitter=params.network_jitter
        )

    return builder.build()


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

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="nimlibp2p2 experiment")
        BaseExperiment.add_args(subparser)

    def _get_metadata(self) -> dict:
        return Bridge().get_metadata(self.events_log_path)

    async def _run(self):
        self.log_event("run_start")

        # Publisher
        publisher = (
            PodApiRequesterBuilder().with_namespace(self.namespace).with_mode("server").build()
        )
        await self.deploy(deployment=publisher, wait_for_ready=True)

        # Nodes
        nodes = build_nodes(
            namespace=self.namespace,
            params=self.config,
        )
        name = nodes.metadata.name
        namespace = nodes.metadata.namespace

        await self.deploy(deployment=nodes)

        logger.info(f"Starting publish loop for nodes in `{name}`")

        self.log_event("start_messages")

        tasks = []
        for msg_index in range(self.config.num_messages):
            index = random.randint(0, self.config.num_nodes - 1)
            random_name = f"{name}-{index}"
            self.log_event({"event": "publish", "node": random_name, "index": msg_index})
            tasks.append(asyncio.create_task(publish(self.config, namespace, random_name)))
            await asyncio.sleep(self.config.delay_after_publish)
        await asyncio.gather(*tasks)

        self.log_event("publisher_messages_finished")

        await asyncio.sleep(20)
        self.log_event("publisher_wait_finished")

        self.log_event("internal_run_finished")
