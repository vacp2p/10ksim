import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

from kubernetes.client import V1Probe, V1ServicePort, V1TCPSocketAction
from pydantic import BaseModel, ConfigDict, NonNegativeInt

from src.analysis.connmanager_analysis import (
    plot_connection_count,
    plot_direction_breakdown,
    plot_trim_timeline,
)
from src.analysis.mesh_analysis.analyzers.connmanager_analyzer import ConnManagerAnalyzer
from src.analysis.mesh_analysis.analyzers.data_puller import DataPuller
from src.deployments.core.builders import ServiceBuilder
from src.deployments.core.configs.container import Image
from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.experiments.multi_experiment import Multiple
from src.deployments.libp2p.bridge import Bridge as Libp2pBridge
from src.deployments.libp2p.builders.builders import Libp2pStatefulSetBuilder
from src.deployments.registry import experiment

logger = logging.getLogger(__name__)

IMAGE_REPO = "radiken/dst-test-node-connmanager"
IMAGE_TAG = "v5"

SCALE_STEPS = [50, 100, 150, 200]
HUB_SCALE_STEPS = [5, 20, 50]

# Default watermark params shared across runs
WATERMARK_LOW = 10
WATERMARK_HIGH = 20
SILENCE_PERIOD_S = 2

READINESS_PROBE = V1Probe(
    tcp_socket=V1TCPSocketAction(port=5000),
    initial_delay_seconds=2,
    period_seconds=5,
)


def _hub_addrs(num_hubs: int, namespace: str) -> str:
    # Each hub pod is individually addressable via the shared headless governance
    # service (nimp2p-service), same pattern as _outbound_peers_str for peers-a.
    return ",".join(
        f"hub-{i}.nimp2p-service.{namespace}.svc.cluster.local:5000" for i in range(num_hubs)
    )


def _outbound_peers_str(num: int, namespace: str) -> str:
    # StatefulSet spec.serviceName is hardcoded to "nimp2p-service" in the builder,
    # so per-pod DNS is peers-a-{i}.nimp2p-service.{namespace}.svc.cluster.local
    return ",".join(
        f"peers-a-{i}.nimp2p-service.{namespace}.svc.cluster.local:5000" for i in range(num)
    )


def _governance_service(namespace: str):
    # Shared headless service required by all StatefulSets — name must match
    # spec.serviceName hardcoded in Libp2pStatefulSetBuilder ("nimp2p-service").
    return (
        ServiceBuilder()
        .with_name("nimp2p-service")
        .with_namespace(namespace)
        .with_cluster_ip("None")
        .with_selector("app", "zerotenkay")
        .with_port(V1ServicePort(name="p2p", port=5000, target_port=5000))
        .build()
    )


class ExpConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run: str = "A"
    image_repo: str = IMAGE_REPO
    image_tag: str = IMAGE_TAG

    # Watermark hub config
    watermark_low: int = WATERMARK_LOW
    watermark_high: int = WATERMARK_HIGH
    grace_period_s: int = 0
    silence_period_s: int = SILENCE_PERIOD_S
    max_connections: int = 0  # 0 = no hard cap; set for Run D

    # Hub count (1 = single hub / existing behaviour; >1 = multi-hub)
    num_hubs: int = 1

    # Peer counts
    num_peers_outbound: NonNegativeInt = 5  # Group A: hub dials them
    num_peers_inbound: NonNegativeInt = 25  # Group B: they dial hub

    # Run C: protected peers
    # Provide hex-encoded secp256k1 private keys for the protected peers.
    # Their peer IDs (derived from these keys) are passed to the hub as PROTECTED_PEERS.
    protected_peer_keys: list[str] = []
    protected_peer_ids: list[str] = []

    # Peer reconnect mode: "none", "aggressive" (Run G), or "before_grace" (Run E)
    reconnect: str = "none"
    reconnect_interval_s: int = 55  # for before_grace: cycle connection every N seconds

    # Run E: how many abuser peers use before_grace mode
    num_abusers: int = 0

    # Run F: number of protected peers (requires protected_peer_keys to be populated)
    num_protected: int = 1

    # How long to let the experiment run before teardown
    run_duration_s: int = 300


@experiment(name="connmanager")
class ConnManagerExperiment(BaseExperiment[ExpConfig]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="Connection manager experiment")
        BaseExperiment.add_base_args(subparser)
        subparser.set_defaults(namespace="nimlibp2p")

    def _get_metadata(self) -> dict:
        return Libp2pBridge().get_metadata(self.events_log_path)

    async def _deploy_services(self, prefix=""):
        hub_svc = (
            ServiceBuilder()
            .with_name("hub")
            .with_namespace(self.namespace)
            .with_selector("app", "zerotenkay")
            .with_selector("role", "hub")
            .with_port(V1ServicePort(name="p2p", port=5000, target_port=5000))
            .build()
        )
        for name, obj in [
            ("hub-svc", hub_svc),
            ("nimp2p-service", _governance_service(self.namespace)),
        ]:
            self.dump_yaml(obj, f"{prefix}{name}")
            await self.deploy(deployment=obj)

    async def _run(self):
        self.log_event("run_start")
        start_time = datetime.now(timezone.utc)

        image = Image(repo=self.config.image_repo, tag=self.config.image_tag)

        run = self.config.run.upper()
        logger.info(f"Starting Run {run}")

        if run == "A":
            await self._run_a(self.config, image)
        elif run == "B":
            await self._run_b(self.config, image)
        elif run == "C":
            await self._run_c(self.config, image)
        elif run == "D":
            await self._run_d(self.config, image)
        elif run == "E":
            await self._run_e(self.config, image)
        elif run == "F":
            await self._run_f(self.config, image)
        elif run == "G":
            await self._run_g(self.config, image)
        else:
            raise ValueError(f"Unknown run: {self.config.run}. Expected A–G.")

        self.log_event("internal_run_finished")
        end_time = datetime.now(timezone.utc)

        self._run_analysis(self.config, start_time, end_time)

    def _run_analysis(self, config, start_time, end_time):
        logger.info("Running post-experiment analysis...")
        try:
            stack = {
                "type": "vaclab",
                "url": "https://vlselect.lab.vac.dev/select/logsql/query",
                "start_time": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end_time": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "reader": "victoria",
                "stateful_sets": ["hub"],
                "nodes_per_statefulset": [1],
                "container_name": "pod-0",
                "namespace": self.namespace,
                "extra_fields": ["kubernetes.pod_name"],
            }

            puller = DataPuller().with_kwargs(stack)
            wave_sets = ["wave1", "wave2"] if config.run.upper() == "B" else None

            analyzer = (
                ConnManagerAnalyzer(
                    dump_analysis_dir=os.path.join(self._workdir, "analysis_data"),
                )
                .with_data_puller(puller)
                .with_hub_analysis(
                    hub_pod="hub-0",
                    grace_period_s=config.grace_period_s,
                    protected_peer_ids=config.protected_peer_ids or None,
                    wave_sets=wave_sets,
                )
            )

            results = analyzer.run()

            out_dir = os.path.join(self._workdir, "plots")
            os.makedirs(out_dir, exist_ok=True)

            for res in results:
                if res.name == "connmanager" and res.intermediates:
                    conn_df = res.intermediates.get("conn_df")
                    drop_df = res.intermediates.get("drop_df")
                    if conn_df is not None and not conn_df.empty:
                        plot_connection_count(conn_df, drop_df, out_dir)
                        plot_direction_breakdown(conn_df, res.intermediates, out_dir)
                        plot_trim_timeline(conn_df, drop_df, out_dir)

            logger.info(f"Analysis complete. Plots saved to {out_dir}")
        except Exception as e:
            logger.error(f"Post-experiment analysis failed: {e}")

    # -------------------------------------------------------------------------
    # Run A: Watermark basics, scoring, performance, oscillation
    # Hub: withWatermark(low, high), reduced silencePeriod
    # Group A peers: hub dials them (outbound bonus)
    # Group B peers: they dial hub (no bonus)
    # -------------------------------------------------------------------------
    async def _run_a(self, config, image):
        hub, peers_a, peers_b = self._build_run_a(config, image)

        await self._deploy_services()
        self.dump_yaml(hub, "hub")
        await self.deploy(deployment=hub, wait_for_ready=True)

        if config.num_peers_outbound > 0:
            self.dump_yaml(peers_a, "peers-a")
            await self.deploy(deployment=peers_a, wait_for_ready=True)

        self.dump_yaml(peers_b, "peers-b")
        await self.deploy(deployment=peers_b, wait_for_ready=True)

        logger.info(f"Run A deployed. Waiting {config.run_duration_s}s.")
        await asyncio.sleep(config.run_duration_s)

    def _build_run_a(self, config, image):
        outbound_peers = _outbound_peers_str(config.num_peers_outbound, self.namespace)

        hub = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(name="hub", namespace=self.namespace, num_nodes=config.num_hubs)
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_label("role", "hub")
            .with_option("NODE_ROLE", "RoleHub")
            .with_option("PORT", "5000")
            .with_option("WATERMARK_LOW", config.watermark_low)
            .with_option("WATERMARK_HIGH", config.watermark_high)
            .with_option("WATERMARK_SILENCE_PERIOD_S", config.silence_period_s)
            .with_option("OUTBOUND_PEERS", outbound_peers)
            .with_option("NUM_HUBS", config.num_hubs)
            .with_option("HUB_NAMESPACE", self.namespace)
            .build()
        )

        peers_a = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="peers-a", namespace=self.namespace, num_nodes=config.num_peers_outbound
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_label("role", "peers-a")
            .with_option("NODE_ROLE", "RolePeer")
            .with_option("PORT", "5000")
            .with_option("DIAL_OUT", "false")
            .build()
        )

        peers_b = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="peers-b", namespace=self.namespace, num_nodes=config.num_peers_inbound
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_label("role", "peers-b")
            .with_option("NODE_ROLE", "RolePeer")
            .with_option("PORT", "5000")
            .with_option("DIAL_OUT", "true")
            .with_option("HUB_ADDRS", _hub_addrs(config.num_hubs, self.namespace))
            .with_option("RECONNECT", config.reconnect)
            .build()
        )

        return hub, peers_a, peers_b

    # -------------------------------------------------------------------------
    # Run B: Grace period correctness + abuse
    # Hub: withWatermark(5, 10, gracePeriod=config.grace_period_s)
    # Wave 1 peers connect early; Wave 2 connect late (within grace window)
    # Phase 2: Wave 2 uses aggressive reconnect to stay grace-exempt
    # -------------------------------------------------------------------------
    async def _run_b(self, config, image):
        await self._deploy_services()

        hub = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(name="hub", namespace=self.namespace, num_nodes=config.num_hubs)
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_label("role", "hub")
            .with_option("NODE_ROLE", "RoleHub")
            .with_option("PORT", "5000")
            .with_option("WATERMARK_LOW", config.watermark_low)
            .with_option("WATERMARK_HIGH", config.watermark_high)
            .with_option("WATERMARK_GRACE_PERIOD_S", config.grace_period_s)
            .with_option("WATERMARK_SILENCE_PERIOD_S", config.silence_period_s)
            .with_option("NUM_HUBS", config.num_hubs)
            .with_option("HUB_NAMESPACE", self.namespace)
            .build()
        )
        self.dump_yaml(hub, "hub")
        await self.deploy(deployment=hub, wait_for_ready=True)

        # Wave 1: connect early, let grace expire before trim fires
        wave1 = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="wave1", namespace=self.namespace, num_nodes=config.num_peers_inbound
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_label("role", "wave1")
            .with_option("NODE_ROLE", "RolePeer")
            .with_option("PORT", "5000")
            .with_option("DIAL_OUT", "true")
            .with_option("HUB_ADDRS", _hub_addrs(config.num_hubs, self.namespace))
            .build()
        )
        self.dump_yaml(wave1, "wave1")
        await self.deploy(deployment=wave1, wait_for_ready=True)

        # Wait for Wave 1 grace period to expire before deploying Wave 2
        grace_buffer_s = config.grace_period_s + 10
        logger.info(f"Waiting {grace_buffer_s}s for Wave 1 grace period to expire.")
        await asyncio.sleep(grace_buffer_s)

        # Wave 2: connect just before trim fires (within grace window)
        wave2 = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="wave2", namespace=self.namespace, num_nodes=config.num_peers_outbound
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_label("role", "wave2")
            .with_option("NODE_ROLE", "RolePeer")
            .with_option("PORT", "5000")
            .with_option("DIAL_OUT", "true")
            .with_option("HUB_ADDRS", _hub_addrs(config.num_hubs, self.namespace))
            .with_option("RECONNECT", config.reconnect)
            .build()
        )
        self.dump_yaml(wave2, "wave2")
        await self.deploy(deployment=wave2, wait_for_ready=True)

        logger.info(f"Run B deployed. Waiting {config.run_duration_s}s.")
        await asyncio.sleep(config.run_duration_s)

    # -------------------------------------------------------------------------
    # Run C: Protection correctness + exhaustion
    # Hub: withWatermark(5, 10), protected peers set via PROTECTED_PEERS env var
    # Protected peers use fixed private keys so their peer IDs are known in advance
    # -------------------------------------------------------------------------
    async def _run_c(self, config, image):
        await self._deploy_services()

        protected_peers_str = ",".join(config.protected_peer_ids)

        hub = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(name="hub", namespace=self.namespace, num_nodes=config.num_hubs)
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_label("role", "hub")
            .with_option("NODE_ROLE", "RoleHub")
            .with_option("PORT", "5000")
            .with_option("WATERMARK_LOW", config.watermark_low)
            .with_option("WATERMARK_HIGH", config.watermark_high)
            .with_option("WATERMARK_SILENCE_PERIOD_S", config.silence_period_s)
            .with_option("PROTECTED_PEERS", protected_peers_str)
            .with_option("NUM_HUBS", config.num_hubs)
            .with_option("HUB_NAMESPACE", self.namespace)
            .build()
        )
        self.dump_yaml(hub, "hub")
        await self.deploy(deployment=hub, wait_for_ready=True)

        protected_keys_str = ",".join(config.protected_peer_keys)
        protected = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="protected",
                namespace=self.namespace,
                num_nodes=len(config.protected_peer_keys),
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_label("role", "protected")
            .with_option("NODE_ROLE", "RolePeer")
            .with_option("PORT", "5000")
            .with_option("DIAL_OUT", "true")
            .with_option("HUB_ADDRS", _hub_addrs(config.num_hubs, self.namespace))
            .with_option("PRIVATE_KEYS", protected_keys_str)
            .build()
        )
        self.dump_yaml(protected, "protected")
        await self.deploy(deployment=protected, wait_for_ready=True)

        # Regular inbound peers
        peers = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="peers", namespace=self.namespace, num_nodes=config.num_peers_inbound
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_label("role", "peers")
            .with_option("NODE_ROLE", "RolePeer")
            .with_option("PORT", "5000")
            .with_option("DIAL_OUT", "true")
            .with_option("HUB_ADDRS", _hub_addrs(config.num_hubs, self.namespace))
            .build()
        )
        self.dump_yaml(peers, "peers")
        await self.deploy(deployment=peers, wait_for_ready=True)

        logger.info(f"Run C deployed. Waiting {config.run_duration_s}s.")
        await asyncio.sleep(config.run_duration_s)

    # -------------------------------------------------------------------------
    # Run D: Hard cap + watermark together
    # Hub: withWatermark(10, 20).withMaxConnections(30)
    # -------------------------------------------------------------------------
    async def _run_d(self, config, image):
        await self._deploy_services()

        hub = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(name="hub", namespace=self.namespace, num_nodes=config.num_hubs)
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_label("role", "hub")
            .with_option("NODE_ROLE", "RoleHub")
            .with_option("PORT", "5000")
            .with_option("WATERMARK_LOW", config.watermark_low)
            .with_option("WATERMARK_HIGH", config.watermark_high)
            .with_option("WATERMARK_SILENCE_PERIOD_S", config.silence_period_s)
            .with_option("MAX_CONNECTIONS", config.max_connections)
            .with_option("NUM_HUBS", config.num_hubs)
            .with_option("HUB_NAMESPACE", self.namespace)
            .build()
        )
        self.dump_yaml(hub, "hub")
        await self.deploy(deployment=hub, wait_for_ready=True)

        peers = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="peers", namespace=self.namespace, num_nodes=config.num_peers_inbound
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_label("role", "peers")
            .with_option("NODE_ROLE", "RolePeer")
            .with_option("PORT", "5000")
            .with_option("DIAL_OUT", "true")
            .with_option("HUB_ADDRS", _hub_addrs(config.num_hubs, self.namespace))
            .build()
        )
        self.dump_yaml(peers, "peers")
        await self.deploy(deployment=peers, wait_for_ready=True)

        logger.info(f"Run D deployed. Waiting {config.run_duration_s}s.")
        await asyncio.sleep(config.run_duration_s)

    # -------------------------------------------------------------------------
    # Run E: Grace period abuse
    # Hub: withWatermark(low, high, gracePeriod=grace_period_s)
    # Abuser peers: reconnect every reconnect_interval_s seconds (< grace_period_s)
    #   to stay perpetually within the grace window.
    # Regular peers: connect and stay.
    # Question: do abusers survive indefinitely?
    # -------------------------------------------------------------------------
    async def _run_e(self, config, image):
        await self._deploy_services()

        hub = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(name="hub", namespace=self.namespace, num_nodes=config.num_hubs)
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_label("role", "hub")
            .with_option("NODE_ROLE", "RoleHub")
            .with_option("PORT", "5000")
            .with_option("WATERMARK_LOW", config.watermark_low)
            .with_option("WATERMARK_HIGH", config.watermark_high)
            .with_option("WATERMARK_GRACE_PERIOD_S", config.grace_period_s)
            .with_option("WATERMARK_SILENCE_PERIOD_S", config.silence_period_s)
            .with_option("NUM_HUBS", config.num_hubs)
            .with_option("HUB_NAMESPACE", self.namespace)
            .build()
        )
        self.dump_yaml(hub, "hub")
        await self.deploy(deployment=hub, wait_for_ready=True)

        # Abuser peers: cycle their connection before grace expires
        abusers = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="abusers", namespace=self.namespace, num_nodes=config.num_abusers
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_label("role", "abusers")
            .with_option("NODE_ROLE", "RolePeer")
            .with_option("PORT", "5000")
            .with_option("DIAL_OUT", "true")
            .with_option("HUB_ADDRS", _hub_addrs(config.num_hubs, self.namespace))
            .with_option("RECONNECT", "before_grace")
            .with_option("RECONNECT_INTERVAL_S", config.reconnect_interval_s)
            .build()
        )
        self.dump_yaml(abusers, "abusers")
        await self.deploy(deployment=abusers, wait_for_ready=True)

        # Regular peers: connect and stay, provide trim pressure
        peers = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="peers", namespace=self.namespace, num_nodes=config.num_peers_inbound
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_label("role", "peers")
            .with_option("NODE_ROLE", "RolePeer")
            .with_option("PORT", "5000")
            .with_option("DIAL_OUT", "true")
            .with_option("HUB_ADDRS", _hub_addrs(config.num_hubs, self.namespace))
            .build()
        )
        self.dump_yaml(peers, "peers")
        await self.deploy(deployment=peers, wait_for_ready=True)

        logger.info(f"Run E deployed. Waiting {config.run_duration_s}s.")
        await asyncio.sleep(config.run_duration_s)

    # -------------------------------------------------------------------------
    # Run F: Protection exhaustion
    # Hub: withWatermark(low, high), num_protected > low (so trim can't reach lowWater)
    # Question: does trim stop cleanly or loop/stall?
    # -------------------------------------------------------------------------
    async def _run_f(self, config, image):
        await self._deploy_services()

        protected_peers_str = ",".join(config.protected_peer_ids)

        hub = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(name="hub", namespace=self.namespace, num_nodes=config.num_hubs)
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_label("role", "hub")
            .with_option("NODE_ROLE", "RoleHub")
            .with_option("PORT", "5000")
            .with_option("WATERMARK_LOW", config.watermark_low)
            .with_option("WATERMARK_HIGH", config.watermark_high)
            .with_option("WATERMARK_SILENCE_PERIOD_S", config.silence_period_s)
            .with_option("PROTECTED_PEERS", protected_peers_str)
            .with_option("NUM_HUBS", config.num_hubs)
            .with_option("HUB_NAMESPACE", self.namespace)
            .build()
        )
        self.dump_yaml(hub, "hub")
        await self.deploy(deployment=hub, wait_for_ready=True)

        # Protected peers: each pod gets its own key via PRIVATE_KEYS (comma-sep list).
        # Pod ordinal (from hostname) selects the correct key.
        protected_keys_str = ",".join(config.protected_peer_keys)
        protected = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="protected", namespace=self.namespace, num_nodes=config.num_protected
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_label("role", "protected")
            .with_option("NODE_ROLE", "RolePeer")
            .with_option("PORT", "5000")
            .with_option("DIAL_OUT", "true")
            .with_option("HUB_ADDRS", _hub_addrs(config.num_hubs, self.namespace))
            .with_option("PRIVATE_KEYS", protected_keys_str)
            .build()
        )
        self.dump_yaml(protected, "protected")
        await self.deploy(deployment=protected, wait_for_ready=True)

        # Regular peers to push past highWater
        peers = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="peers", namespace=self.namespace, num_nodes=config.num_peers_inbound
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_label("role", "peers")
            .with_option("NODE_ROLE", "RolePeer")
            .with_option("PORT", "5000")
            .with_option("DIAL_OUT", "true")
            .with_option("HUB_ADDRS", _hub_addrs(config.num_hubs, self.namespace))
            .build()
        )
        self.dump_yaml(peers, "peers")
        await self.deploy(deployment=peers, wait_for_ready=True)

        logger.info(f"Run F deployed. Waiting {config.run_duration_s}s.")
        await asyncio.sleep(config.run_duration_s)

    # -------------------------------------------------------------------------
    # Run G: Oscillation
    # Hub: withWatermark(low, high), reduced silencePeriod
    # Peers reconnect immediately after being dropped (ReconnectAggressive).
    # Question: does the hub stabilise or keep cycling?
    # -------------------------------------------------------------------------
    async def _run_g(self, config, image):
        await self._deploy_services()

        hub = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(name="hub", namespace=self.namespace, num_nodes=config.num_hubs)
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_label("role", "hub")
            .with_option("NODE_ROLE", "RoleHub")
            .with_option("PORT", "5000")
            .with_option("WATERMARK_LOW", config.watermark_low)
            .with_option("WATERMARK_HIGH", config.watermark_high)
            .with_option("WATERMARK_SILENCE_PERIOD_S", config.silence_period_s)
            .with_option("NUM_HUBS", config.num_hubs)
            .with_option("HUB_NAMESPACE", self.namespace)
            .build()
        )
        self.dump_yaml(hub, "hub")
        await self.deploy(deployment=hub, wait_for_ready=True)

        peers = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="peers", namespace=self.namespace, num_nodes=config.num_peers_inbound
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_label("role", "peers")
            .with_option("NODE_ROLE", "RolePeer")
            .with_option("PORT", "5000")
            .with_option("DIAL_OUT", "true")
            .with_option("HUB_ADDRS", _hub_addrs(config.num_hubs, self.namespace))
            .with_option("RECONNECT", "aggressive")
            .build()
        )
        self.dump_yaml(peers, "peers")
        await self.deploy(deployment=peers, wait_for_ready=True)

        logger.info(f"Run G deployed. Waiting {config.run_duration_s}s.")
        await asyncio.sleep(config.run_duration_s)


# -------------------------------------------------------------------------
# Scale experiments using the Multiple pipeline.
# Each step runs the base "connmanager" experiment with different params,
# getting its own output folder and metadata.json.
# -------------------------------------------------------------------------


@experiment(name="connmanager-a-scale")
class ConnManagerAScale(Multiple):
    """Run A at increasing peer counts (50/100/150/200).
    Watermarks scale proportionally: lowWater=n//2, highWater=n.
    """

    def model_post_init(self, __context: Any) -> None:
        self.config.name = "connmanager"
        self.config.delay = 15
        super().model_post_init(__context)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="Run A at scale steps")
        Multiple.add_base_args(subparser)
        BaseExperiment.add_base_args(subparser)
        subparser.set_defaults(namespace="nimlibp2p")

    def get_params_list(self) -> list[dict]:
        return [
            {
                "run": "A",
                "watermark_low": n // 2,
                "watermark_high": n,
                "num_peers_inbound": n + 20,
                "num_peers_outbound": 0,
            }
            for n in SCALE_STEPS
        ]


@experiment(name="connmanager-e-scale")
class ConnManagerEScale(Multiple):
    """Run E (grace abuse) at increasing peer counts.
    Watermark fixed at defaults (same as original Run E) so timing is comparable.
    Abusers are 1/3 of n; the rest are regular peers.
    """

    def model_post_init(self, __context: Any) -> None:
        self.config.name = "connmanager"
        self.config.delay = 15
        super().model_post_init(__context)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="Run E at scale steps")
        Multiple.add_base_args(subparser)
        BaseExperiment.add_base_args(subparser)
        subparser.set_defaults(namespace="nimlibp2p")

    def get_params_list(self) -> list[dict]:
        return [
            {
                "run": "E",
                "num_abusers": n // 3,
                "num_peers_inbound": n - n // 3,
            }
            for n in SCALE_STEPS
        ]


@experiment(name="connmanager-g-scale")
class ConnManagerGScale(Multiple):
    """Run G (oscillation) at increasing peer counts.
    Watermarks scale proportionally: lowWater=n//2, highWater=n.
    """

    def model_post_init(self, __context: Any) -> None:
        self.config.name = "connmanager"
        self.config.delay = 15
        super().model_post_init(__context)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="Run G at scale steps")
        Multiple.add_base_args(subparser)
        BaseExperiment.add_base_args(subparser)
        subparser.set_defaults(namespace="nimlibp2p")

    def get_params_list(self) -> list[dict]:
        return [
            {
                "run": "G",
                "watermark_low": n // 2,
                "watermark_high": n,
                "num_peers_inbound": n + 20,
            }
            for n in SCALE_STEPS
        ]


@experiment(name="connmanager-hub-scale")
class ConnManagerHubScale(Multiple):
    """Hub-scale: fixed peer count, hub count varies (5/20/50).
    Uses Run A deployment pattern with varying num_hubs.
    """

    def model_post_init(self, __context: Any) -> None:
        self.config.name = "connmanager"
        self.config.delay = 15
        super().model_post_init(__context)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="Run A with varying hub counts")
        Multiple.add_base_args(subparser)
        BaseExperiment.add_base_args(subparser)
        subparser.set_defaults(namespace="nimlibp2p")

    def get_params_list(self) -> list[dict]:
        return [{"run": "A", "num_hubs": n} for n in HUB_SCALE_STEPS]
