import asyncio
import logging
import os
from argparse import Namespace
from contextlib import ExitStack
from pathlib import Path
from typing import Optional

from kubernetes.client import ApiClient, V1ServicePort
from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

from src.deployments.core.builders import ServiceBuilder
from src.deployments.core.configs.container import Image
from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.libp2p.builders.builders import Libp2pStatefulSetBuilder
from src.deployments.registry import experiment

logger = logging.getLogger(__name__)


@experiment(name="kad-dht")
class KadDHTExperiment(BaseExperiment, BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="KAD DHT experiment")
        BaseExperiment.add_args(subparser)
        subparser.set_defaults(namespace="nimlibp2p")

    class ExpConfig(BaseModel):
        model_config = ConfigDict(extra="ignore")

        num_nodes: NonNegativeInt = 80
        warmup_delay: NonNegativeFloat = 0
        probe_delay: NonNegativeFloat = 600
        image_repo: str = "radiken/dst-test-node-kad-dht"
        image_tag: str = "long-logs"

    async def _run(
        self,
        api_client: ApiClient,
        workdir: str,
        args: Namespace,
        values_yaml: Optional[dict],
        stack: ExitStack,
    ):
        self.log_event("run_start")

        values_yaml = values_yaml or {}
        config = self.ExpConfig(**values_yaml)
        self.log_metadata({"params": vars(config)})
        namespace = args.namespace
        image = Image(repo=config.image_repo, tag=config.image_tag)

        # 1. Build and Deploy Headless Bootstrap Service
        bootstrap_service = (
            ServiceBuilder()
            .with_name("bootstrap")
            .with_namespace(namespace)
            .with_cluster_ip("None")
            .with_selector("app", "zerotenkay")
            .with_selector("role", "bootstrap")
            .with_port(V1ServicePort(name="p2p", port=5000, target_port=5000))
            .build()
        )
        self.dump_yaml(bootstrap_service, workdir, "bootstrap-service")
        await self.deploy(api_client, stack, args, values_yaml, deployment=bootstrap_service)

        # 2. Build and Deploy Bootstrap Node
        bootstrap_nodes = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(name="bootstrap", namespace=namespace, num_nodes=1)
            .with_image(image)
            .with_label("role", "bootstrap")
            .with_option("NODE_ROLE", "RoleBootstrap")
            .with_option("PORT", "5000")
            .with_option("DISCOVERY", "kad-dht")
            .with_readiness_probe(path="/ready", port=8008)
            .build()
        )
        self.dump_yaml(bootstrap_nodes, workdir, "bootstrap")
        await self.deploy(api_client, stack, args, values_yaml, deployment=bootstrap_nodes, wait_for_ready=True)

        # 3. Build and Deploy Regular Nodes
        nodes = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(name="nodes", namespace=namespace, num_nodes=config.num_nodes)
            .with_image(image)
            .with_label("role", "nodes")
            .with_option("NODE_ROLE", "RoleNormal")
            .with_option("PORT", "5000")
            .with_option("DISCOVERY", "kad-dht")
            .with_option("SERVICE", f"bootstrap.{namespace}.svc.cluster.local")
            .with_readiness_probe(path="/ready", port=8008)
            .build()
        )
        self.dump_yaml(nodes, workdir, "nodes")
        await self.deploy(api_client, stack, args, values_yaml, deployment=nodes, wait_for_ready=True)

        # 4. Wait for Warmup
        if config.warmup_delay > 0:
            logger.info(f"Waiting {config.warmup_delay} seconds for DHT warmup...")
            await asyncio.sleep(config.warmup_delay)

        # 5. Build and Deploy Probe
        probe = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(name="probe", namespace=namespace, num_nodes=1)
            .with_image(image)
            .with_label("role", "probe")
            .with_option("NODE_ROLE", "RoleProbe")
            .with_option("PORT", "5000")
            .with_option("DISCOVERY", "kad-dht")
            .with_option("SERVICE", f"bootstrap.{namespace}.svc.cluster.local")
            .build()
        )
        self.dump_yaml(probe, workdir, "probe")
        await self.deploy(api_client, stack, args, values_yaml, deployment=probe, wait_for_ready=True)

        # 6. Wait for Probe Execution
        if config.probe_delay > 0:
            logger.info(f"Waiting {config.probe_delay} seconds for probe to execute lookups...")
            await asyncio.sleep(config.probe_delay)

        self.log_event("internal_run_finished")
