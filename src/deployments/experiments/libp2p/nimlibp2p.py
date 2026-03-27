import asyncio
import logging
import os
import random
import traceback
from argparse import Namespace
from contextlib import ExitStack
from pathlib import Path
from typing import Optional

from kubernetes.client import ApiClient, V1StatefulSet
from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

from src.deployments.core.kube_utils import get_YAML, k8s_obj_to_dict
from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.libp2p.bridge import Bridge
from src.deployments.libp2p.builders.builders import Libp2pStatefulSetBuilder
from src.deployments.libp2p.builders.builders import Option as NimLibp2p
from src.deployments.pod_api_requester.builder import PodApiRequesterBuilder
from src.deployments.pod_api_requester.configs import Target
from src.deployments.pod_api_requester.nimlibp2p import libp2p_dst_node_publish
from src.deployments.pod_api_requester.pod_api_requester import PodApiApplicationError, PodApiError
from src.deployments.registry import experiment

logger = logging.getLogger(__name__)


def build_nodes(
    namespace: str,
    num_nodes: int,
) -> V1StatefulSet:
    return (
        Libp2pStatefulSetBuilder()
        .with_libp2p_config(name="pod", namespace=namespace, num_nodes=num_nodes)
        .with_option(NimLibp2p.peers, num_nodes)
        .with_option(NimLibp2p.muxer, "yamux")
        .with_option(NimLibp2p.connect_to, 10)
        .build()
    )


@experiment(name="nimlibp2p")
class NimLibp2pExperiment(BaseExperiment, BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="nimlibp2p2 experiment")
        BaseExperiment.add_args(subparser)

    def _get_metadata(self) -> dict:
        return Bridge().get_metadata(self.events_log_path)

    class ExpConfig(BaseModel):
        model_config = ConfigDict(extra="ignore")

        num_nodes: NonNegativeInt = 20
        num_messages: NonNegativeInt = 20
        message_size_kb: NonNegativeInt = 1
        delay_cold_start: NonNegativeFloat = 60
        delay_after_publish: NonNegativeFloat = 1

    async def _run(
        self,
        api_client: ApiClient,
        workdir: str,
        args: Namespace,
        values_yaml: Optional[dict],
        stack: ExitStack,
    ):
        self.log_event("run_start")

        config = self.ExpConfig(**values_yaml)
        self.log_metadata({"params": vars(config)})

        # Publisher
        publisher = (
            PodApiRequesterBuilder().with_namespace(args.namespace).with_mode("server").build()
        )
        await self.deploy(
            api_client, stack, args, values_yaml, deployment=publisher, wait_for_ready=True
        )

        # Nodes
        nodes = build_nodes(
            namespace=args.namespace,
            num_nodes=config.num_nodes,
        )
        name = nodes.metadata.name
        namespace = nodes.metadata.namespace

        out_path = Path(workdir) / name / f"{name}.yaml"
        os.makedirs(out_path.parent, exist_ok=True)
        logger.info(f"dumping deployment `{name}` to `{out_path}`")
        with open(out_path, "w") as out_file:
            yaml = get_YAML()
            yaml.dump(k8s_obj_to_dict(nodes), out_file)
        await self.deploy(api_client, stack, args, values_yaml, deployment=nodes)

        await asyncio.sleep(config.delay_cold_start)

        logger.info(f"Starting publish loop for nodes in `{name}`")

        self.log_event("start_messages")

        for _ in range(config.num_messages):
            index = random.randint(0, config.num_nodes - 1)
            random_name = f"{name}-{index}"
            self.log_event({"event": "publish", "node": random_name})
            try:
                target = Target(
                    name="libp2p-node",
                    name_template=random_name,
                    service="nimp2p-service",
                    port=8645,
                )
                await libp2p_dst_node_publish(
                    namespace=namespace, target=target, msg_size_kbytes=config.message_size_kb
                )
            except PodApiApplicationError as e:
                logger.error(f"PodApiApplicationError: {e} {traceback.format_exc()}")
            except PodApiError as e:
                logger.error(f"PodApiError: {e} {traceback.format_exc()}")
            except Exception as e:
                logger.error(f"Other exception: {e} {traceback.format_exc()}")

            await asyncio.sleep(config.delay_after_publish)

        self.log_event("publisher_messages_finished")

        await asyncio.sleep(20)
        self.log_event("publisher_wait_finished")

        self.log_event("internal_run_finished")
