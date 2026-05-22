import asyncio
import logging
import random
import traceback
from typing import Dict

from kubernetes import client
from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

from src.deployments.core.configs.statefulset import StatefulSetConfig
from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.libp2p.builders.nodes import Nodes
from src.deployments.pod_api_requester.builder import PodApiRequesterBuilder
from src.deployments.pod_api_requester.configs import Target
from src.deployments.pod_api_requester.pod_api_requester import PodApiApplicationError, PodApiError
from src.deployments.pod_api_requester.waku import waku_publish
from src.deployments.registry import experiment
from src.deployments.waku.bridge import Bridge
from src.deployments.waku.builders.builders import WakuStatefulSetBuilder

logger = logging.getLogger(__name__)


def build_nodes(
    namespace: str, nodes: NonNegativeInt, bootstrap_nodes: NonNegativeInt
) -> Dict[str, dict]:
    config = StatefulSetConfig()
    api_client = client.ApiClient()

    def to_dict(deployment) -> dict:
        return api_client.sanitize_for_serialization(deployment)

    builder = WakuStatefulSetBuilder()
    nodes = (
        builder.with_waku_config(name="nodes-0", namespace=namespace, num_nodes=nodes)
        .with_regression()
        .build()
    )

    bootstrap = (
        WakuStatefulSetBuilder(config=config)
        .with_waku_config(name="bootstrap", namespace=namespace, num_nodes=bootstrap_nodes)
        .with_bootstrap()
        .with_args({"--max-connections": 500}, on_duplicate="replace")
        .build()
    )

    return {
        "bootstrap": to_dict(bootstrap),
        "nodes": to_dict(nodes),
    }


def build_store_nodes(namespace: str) -> dict:
    config = StatefulSetConfig()
    builder = WakuStatefulSetBuilder(config)

    deployment = (
        builder.with_waku_config(name="store-0", namespace=namespace, num_nodes=10)
        .with_args(Nodes.create_standard_args())
        .with_enr(3, [f"zerotesting-bootstrap.{namespace}"])
        .with_store()
        .build()
    )

    api_client = client.ApiClient()
    return api_client.sanitize_for_serialization(deployment)


class ExpConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    num_messages: NonNegativeInt = 20
    num_nodes: NonNegativeInt = 20
    num_bootstrap_nodes: NonNegativeInt = 5
    delay_cold_start: NonNegativeFloat = 1
    delay_after_publish: NonNegativeFloat = 0.5


@experiment(name="waku")
class WakuExperiment(BaseExperiment[ExpConfig]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="Dummy experiment to run and test things.")
        BaseExperiment.add_args(subparser)

    def _get_metadata(self) -> dict:
        return Bridge().get_metadata(self.events_log_path)

    def log_event(self, event):
        logger.info(event)
        return super().log_event(event)

    async def _run(self):
        self.log_event("run_start")


        # Publisher
        publisher = (
            PodApiRequesterBuilder()
            .with_namespace(self.namespace)
            .with_mode("server")
            # .with_debug()
            # .with_image(Image(repo="pearsonwhite/pod-api-requester", tag="9497aebc1483572b5bd4a4712bfcb76a63d04cf8"))
            .build()
        )

        await self.deploy(deployment=publisher, wait_for_ready=True)

        # Nodes
        deployments = build_nodes(
            self.namespace, self.config.num_nodes, self.config.num_bootstrap_nodes
        )
        for deployment in deployments.values():
            await self.deploy(deployment=deployment)

        await asyncio.sleep(self.config.delay_cold_start)
        nodes = deployments["nodes"]
        num_nodes = nodes["spec"]["replicas"]
        name = nodes["metadata"]["name"]
        namespace = nodes["metadata"]["namespace"]
        logger.info(f"Starting disconnect+publish loop for nodes in `{name}`")
        self.log_event("start_messages")
        for _ in range(0, self.config.num_messages):
            index = random.randint(0, num_nodes - 1)
            random_name = f"{name}-{index}"
            self.log_event({"event": "publish", "node": random_name})
            try:
                target = Target(
                    name="waku-node",
                    name_template=random_name,
                    service="zerotesting-service",
                    port=8645,
                )
                await waku_publish(namespace=namespace, target=target)
            except PodApiApplicationError as e:
                logger.error(f"PodApiApplicationError: {e} {traceback.format_exc()}")
            except PodApiError as e:
                logger.error(f"PodApiError: {e} {traceback.format_exc()}")
            except Exception as e:
                logger.error(f"Other exception: {e} {traceback.format_exc()}")

            await asyncio.sleep(self.config.delay_after_publish)

        self.log_event("publisher_messages_finished")

        await asyncio.sleep(20)
        self.log_event("publisher_wait_finished")

        self.log_event("internal_run_finished")
