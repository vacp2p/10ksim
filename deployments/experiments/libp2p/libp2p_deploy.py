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
from pod_api_requester.pod_api_requester import PodApiApplicationError, PodApiError, request
from registry import experiment

from libp2p.builders.builders import Libp2pStatefulSetBuilder, create_mix_pvc

logger = logging.getLogger(__name__)


def build_nodes(
    namespace: str,
    num_nodes: int,
    with_mix: bool,
    num_mix: int,
    mix_d: int,
    network_delay_ms: Optional[int],
    network_jitter_ms: int,
) -> Dict[str, dict]:
    api_client = client.ApiClient()

    def to_dict(deployment) -> dict:
        return api_client.sanitize_for_serialization(deployment)

    result = {}

    # Build StatefulSet
    builder = Libp2pStatefulSetBuilder(config=StatefulSetConfig())
    builder.with_libp2p_config(name="pod", namespace=namespace, num_nodes=num_nodes)

    # Add network delay if specified
    if network_delay_ms is not None:
        builder.with_network_delay(
            delay_ms=network_delay_ms,
            jitter_ms=network_jitter_ms,
        )

    # Add mix protocol if enabled
    if with_mix:
        pvc = create_mix_pvc(namespace=namespace)
        result["pvc"] = to_dict(pvc)
        builder.with_mix(num_mix=num_mix, mix_d=mix_d)

    nodes = builder.build()
    result["nodes"] = to_dict(nodes)

    return result


@experiment(name="libp2p-deployment")
class Libp2pDeploymentExperiment(BaseExperiment, BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="Libp2p deployment with pod_api_requester.")
        BaseExperiment.add_args(subparser)

    def log_event(self, event):
        logger.info(event)
        return super().log_event(event)

    class ExpConfig(BaseModel):
        model_config = ConfigDict(extra="ignore")

        # Node configuration
        num_nodes: NonNegativeInt = 10
        num_messages: NonNegativeInt = 20
        delay_cold_start: NonNegativeFloat = 60
        delay_after_publish: NonNegativeFloat = 1
        # Mix protocol options
        with_mix: bool = False
        num_mix: NonNegativeInt = 10
        mix_d: NonNegativeInt = 3
        # Network delay options
        network_delay_ms: Optional[NonNegativeInt] = None
        network_jitter_ms: NonNegativeInt = 30

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

        # Log configuration
        delay_str = f"{config.network_delay_ms}ms" if config.network_delay_ms is not None else "disabled"
        logger.info(f"Configuration: nodes={config.num_nodes}, mix={config.with_mix}, delay={delay_str}")

        # Publisher
        publisher = (
            PodApiRequesterBuilder()
            .with_namespace(args.namespace)
            .with_mode("server")
            .build()
        )

        await self.deploy(
            api_client, stack, args, values_yaml, deployment=publisher, wait_for_ready=True
        )

        # Nodes (with optional mix and delay support)
        deployments = build_nodes(
            namespace=args.namespace,
            num_nodes=config.num_nodes,
            with_mix=config.with_mix,
            num_mix=config.num_mix,
            mix_d=config.mix_d,
            network_delay_ms=config.network_delay_ms,
            network_jitter_ms=config.network_jitter_ms,
        )
        nodes = deployments["nodes"]

        # Deploy PVC first if using mix
        if "pvc" in deployments:
            pvc = deployments["pvc"]
            name = pvc["metadata"]["name"]
            out_path = Path(workdir) / name / f"{name}.yaml"
            os.makedirs(out_path.parent, exist_ok=True)
            logger.info(f"dumping PVC `{name}` to `{out_path}`")
            with open(out_path, "w") as out_file:
                yaml = get_YAML()
                yaml.dump(pvc, out_file)
            await self.deploy(api_client, stack, args, values_yaml, deployment=pvc)

        # Deploy nodes
        name = nodes["metadata"]["name"]
        out_path = Path(workdir) / name / f"{name}.yaml"
        os.makedirs(out_path.parent, exist_ok=True)
        logger.info(f"dumping deployment `{name}` to `{out_path}`")
        with open(out_path, "w") as out_file:
            yaml = get_YAML()
            yaml.dump(nodes, out_file)
        await self.deploy(api_client, stack, args, values_yaml, deployment=nodes)

        await asyncio.sleep(config.delay_cold_start)
        num_nodes = nodes["spec"]["replicas"]
        name = nodes["metadata"]["name"]
        namespace = nodes["metadata"]["namespace"]
        logger.info(f"Starting publish loop for nodes in `{name}`")

        for _ in range(config.num_messages):
            index = random.randint(0, num_nodes - 1)
            random_name = f"{name}-{index}"
            self.log_event({"event": "publish", "node": random_name})
            try:
                target = Target(
                    name="libp2p-node",
                    name_template=random_name,
                    service="nimp2p-service",
                    port=8645,
                )
                await request(
                    namespace=namespace, target=target, endpoint="libp2p-dst-node-publish"
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
