import asyncio
import logging

from kubernetes.client import V1HTTPGetAction, V1Probe, V1ServicePort
from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

from src.deployments.core.builders import ServiceBuilder
from src.deployments.core.configs.container import Image
from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.libp2p.builders.builders import Libp2pStatefulSetBuilder
from src.deployments.registry import experiment

logger = logging.getLogger(__name__)


class ExpConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    num_nodes: NonNegativeInt = 80
    warmup_delay: NonNegativeFloat = 0
    probe_delay: NonNegativeFloat = 60
    image_repo: str = "radiken/dst-test-node-kad-dht"
    image_tag: str = "melodie-fix"


@experiment(name="kad-dht")
class KadDHTExperiment(BaseExperiment[ExpConfig]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="KAD DHT experiment")
        BaseExperiment.add_base_args(subparser)
        subparser.set_defaults(namespace="nimlibp2p")

    async def _run(self):
        self.log_event("run_start")

        namespace = self.namespace
        image = Image(repo=self.config.image_repo, tag=self.config.image_tag)

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
        self.dump_yaml(bootstrap_service, "bootstrap-service")
        await self.deploy(deployment=bootstrap_service)

        # 2. Build and Deploy Bootstrap Node
        bootstrap_nodes = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(name="bootstrap", namespace=namespace, num_nodes=1)
            .with_image(image)
            .with_label("role", "bootstrap")
            .with_option("NODE_ROLE", "RoleBootstrap")
            .with_option("PORT", "5000")
            .with_option("DISCOVERY", "kad-dht")
            .with_readiness_probe(
                V1Probe(
                    http_get=V1HTTPGetAction(path="/ready", port=8008),
                    initial_delay_seconds=2,
                    period_seconds=2,
                )
            )
            .build()
        )
        self.dump_yaml(bootstrap_nodes, "bootstrap")
        await self.deploy(deployment=bootstrap_nodes, wait_for_ready=True)

        # 3. Build and Deploy Regular Nodes
        nodes = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(name="nodes", namespace=namespace, num_nodes=self.config.num_nodes)
            .with_image(image)
            .with_label("role", "nodes")
            .with_option("NODE_ROLE", "RoleNormal")
            .with_option("PORT", "5000")
            .with_option("DISCOVERY", "kad-dht")
            .with_option("SERVICE", f"bootstrap.{namespace}.svc.cluster.local")
            .with_readiness_probe(
                V1Probe(
                    http_get=V1HTTPGetAction(path="/ready", port=8008),
                    initial_delay_seconds=2,
                    period_seconds=2,
                )
            )
            .build()
        )
        self.dump_yaml(nodes, "nodes")
        await self.deploy(deployment=nodes, wait_for_ready=True)

        # 4. Wait for Warmup
        if self.config.warmup_delay > 0:
            logger.info(f"Waiting {self.config.warmup_delay} seconds for DHT warmup...")
            await asyncio.sleep(self.config.warmup_delay)

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
        self.dump_yaml(probe, "probe")
        await self.deploy(deployment=probe, wait_for_ready=True)

        # 6. Wait for Probe Execution
        if self.config.probe_delay > 0:
            logger.info(
                f"Waiting {self.config.probe_delay} seconds for probe to execute lookups..."
            )
            await asyncio.sleep(self.config.probe_delay)

        self.log_event("internal_run_finished")
