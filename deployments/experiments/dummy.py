import asyncio
import logging
import os
import random
import traceback
from argparse import Namespace
from contextlib import ExitStack
from pathlib import Path
from typing import Dict, Optional

from kubernetes import client
from kubernetes.client import ApiClient
from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

from core.configs.statefulset import StatefulSetConfig
from core.kube_utils import get_YAML
from experiments.base_experiment import BaseExperiment
from pod_api_requester.builder import PodApiRequesterBuilder
from pod_api_requester.configs import Target
from pod_api_requester.pod_api_requester import PodApiApplicationError, PodApiError
from pod_api_requester.waku import waku_publish
from registry import experiment
from waku.builders import WakuStatefulSetBuilder
from waku.builders.nodes import Nodes

logger = logging.getLogger(__name__)


def build_nodes(namespace: str) -> Dict[str, dict]:
    config = StatefulSetConfig()
    api_client = client.ApiClient()

    def to_dict(deployment) -> dict:
        return api_client.sanitize_for_serialization(deployment)

    builder = WakuStatefulSetBuilder()
    nodes = (
        builder.with_waku_config(name="nodes-0", namespace=namespace, num_nodes=10)
        .with_regression()
        .build()
    )

    bootstrap = (
        WakuStatefulSetBuilder(config=config)
        .with_waku_config(name="bootstrap", namespace=namespace, num_nodes=5)
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


@experiment(name="dummy")
class DummyExperiment(BaseExperiment, BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="Dummy experiment to run and test things.")
        BaseExperiment.add_args(subparser)

    def log_event(self, event):
        logger.info(event)
        return super().log_event(event)

    def log_event(self, event):
        logger.info(event)
        return super().log_event(event)

    class ExpConfig(BaseModel):
        model_config = ConfigDict(extra="ignore")

        num_messages: NonNegativeInt = 20
        delay_cold_start: NonNegativeFloat = 1
        delay_after_publish: NonNegativeFloat = 0.5

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

        # Publisher
        publisher = (
            PodApiRequesterBuilder()
            .with_namespace(args.namespace)
            .with_mode("server")
            #  .with_debug()
            .build()
        )

        await self.deploy(
            api_client, stack, args, values_yaml, deployment=publisher, wait_for_ready=True
        )

        # Nodes
        deployments = build_nodes(args.namespace)
        nodes = deployments["nodes"]
        bootstrap = deployments["bootstrap"]
        for deployment in deployments.values():
            name = deployment["metadata"]["name"]
            out_path = Path(workdir) / name / f"{name}.yaml"
            os.makedirs(out_path.parent, exist_ok=True)
            logger.info(f"dumping deployment `{name}` to `{out_path}`")
            with open(out_path, "w") as out_file:
                yaml = get_YAML()
                yaml.dump(deployment, out_file)
            await self.deploy(api_client, stack, args, values_yaml, deployment=deployment)

        await asyncio.sleep(config.delay_cold_start)
        num_nodes = nodes["spec"]["replicas"]
        name = nodes["metadata"]["name"]
        namespace = nodes["metadata"]["namespace"]
        logger.info(f"Starting disconnect+publish loop for nodes in `{name}`")
        for _ in range(0, config.num_messages):
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

            await asyncio.sleep(config.delay_after_publish)

        self.log_event("publisher_messages_finished")

        await asyncio.sleep(20)
        self.log_event("publisher_wait_finished")

        self.log_event("internal_run_finished")
