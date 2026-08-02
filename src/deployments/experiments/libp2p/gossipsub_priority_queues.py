import asyncio
import logging
from typing import List, Optional

import yaml
from kubernetes.client import V1Probe, V1ResourceRequirements, V1ServicePort, V1TCPSocketAction
from pydantic import BaseModel, ConfigDict

from src.deployments.core.builders import ServiceBuilder
from src.deployments.core.configs.container import Image
from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.libp2p.bridge import Bridge as Libp2pBridge
from src.deployments.libp2p.builders.builders import Libp2pStatefulSetBuilder
from src.deployments.libp2p.builders.builders import Option as NimLibp2p
from src.deployments.libp2p.builders.helpers import find_libp2p_container_config
from src.deployments.pod_api_requester.builder import PodApiRequesterBuilder
from src.deployments.registry import experiment

logger = logging.getLogger(__name__)


class ExpConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Scenario selector
    scenario: str = "S0"

    # Image config
    image_repo: str = "mamoutoudiarra/nim-libp2p-test"
    image_tag: str = "gossip-queues-v0.4"
    publisher_image_repo: str = "mamoutoudiarra/pod-api-requester"
    publisher_image_tag: str = "v0.3"

    # Node counts
    num_normal_nodes: int = 1
    num_slow_nodes: int = 1
    total_peers: int = 2

    # Connection config
    connect_to: int = 1
    muxer: str = "yamux"

    # GossipSub mesh params
    gossipsub_d: int = 1
    gossipsub_d_low: int = 0
    gossipsub_d_high: int = 2
    gossipsub_d_out: int = 1
    gossipsub_d_lazy: int = 1

    # Priority queue sizes
    high_queue_size: int = 256
    medium_queue_size: int = 32
    low_queue_size: int = 1024

    # Slow peer penalty params
    slow_peer_penalty_weight: float = 0.0
    slow_peer_penalty_decay: float = 0.2

    # Bandwidth limiting (tc-based)
    slow_ingress_bandwidth: Optional[str] = "512kbit"
    slow_egress_bandwidth: Optional[str] = None

    # Publisher config
    num_messages: int = 180
    message_size_bytes: int = 262144  # 256 KB
    message_rate_per_sec: float = 1.0
    publish_from_role: str = "normal"  # "normal", "slow", "all"
    publish_order: str = "random"

    # Dual publisher config (for scenarios with background + burst patterns)
    use_dual_publishers: bool = False
    background_message_size_bytes: int = 1024  # 1 KB
    background_rate_per_sec: float = 0.2
    background_targets: str = "both"  # "normal", "slow", "both"
    burst_message_size_bytes: int = 131072  # 128 KB
    burst_rate_per_sec: float = 128.0
    burst_size: int = 512
    burst_interval_sec: int = 120  # Delay between bursts
    burst_targets: str = "normal"  # "normal", "slow", "both"
    dual_publisher_start_delay_sec: int = 60  # Delay before starting burst publisher

    # Timing
    delay_cold_start: int = 30
    run_duration_s: int = 300


@experiment(name="gossipsub-priority-queues")
class GossipSubPriorityQueuesExperiment(BaseExperiment[ExpConfig]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_metadata(self) -> dict:
        return Libp2pBridge().get_metadata(self.events_log_path)

    async def _run(self):
        # Apply scenario defaults
        self._apply_scenario_defaults()

        self.log_event(
            {
                "event": "run_start",
                "scenario": self.config.scenario,
                "num_normal_nodes": self.config.num_normal_nodes,
                "num_slow_nodes": self.config.num_slow_nodes,
            }
        )

        # Deploy
        await self._deploy_scenario()

        self.log_event("internal_run_finished")

    def _apply_scenario_defaults(self):
        """Apply scenario-specific defaults if not overridden by CLI."""
        scenario = self.config.scenario.upper()

        if scenario == "S0":
            self._set_defaults_s0()
        elif scenario == "S1":
            self._set_defaults_s1()
        elif scenario == "S2":
            self._set_defaults_s2()
        elif scenario == "S3":
            self._set_defaults_s3()
        elif scenario == "S4-1" or scenario == "S4.1":
            self._set_defaults_s4_1()
        elif scenario == "S4-2" or scenario == "S4.2":
            self._set_defaults_s4_2()
        elif scenario == "S5":
            self._set_defaults_s5()

    def _set_default(self, key: str, value):
        """Set config value only if it's the class default."""
        current = getattr(self.config, key)
        default_config = ExpConfig()
        if current == getattr(default_config, key):
            setattr(self.config, key, value)

    def _set_defaults_s0(self):
        """S0: Regression test - 100 nodes, no slow peers"""
        self._set_default("num_normal_nodes", 100)
        self._set_default("num_slow_nodes", 0)
        self._set_default("total_peers", 10)
        self._set_default("connect_to", 6)
        self._set_default("gossipsub_d", 6)
        self._set_default("gossipsub_d_high", 8)
        self._set_default("gossipsub_d_low", 4)
        self._set_default("num_messages", 900)
        self._set_default("message_size_bytes", 1024)

    def _set_defaults_s1(self):
        """S1: Medium queue overflow"""
        self._set_default("num_normal_nodes", 1)
        self._set_default("num_slow_nodes", 1)
        self._set_default("total_peers", 2)
        self._set_default("connect_to", 1)
        self._set_default("gossipsub_d", 1)
        self._set_default("gossipsub_d_high", 2)
        self._set_default("gossipsub_d_low", 0)
        self._set_default("high_queue_size", 256)
        self._set_default("medium_queue_size", 32)
        self._set_default("low_queue_size", 1024)
        self._set_default("slow_ingress_bandwidth", "1mbit")
        self._set_default("num_messages", 180)
        self._set_default("message_size_bytes", 262144)

    def _set_defaults_s2(self):
        """S2: Low queue overflow"""
        self._set_default("num_normal_nodes", 19)
        self._set_default("num_slow_nodes", 1)
        self._set_default("total_peers", 20)
        self._set_default("connect_to", 10)
        self._set_default("gossipsub_d", 6)
        self._set_default("gossipsub_d_high", 8)
        self._set_default("gossipsub_d_low", 4)
        self._set_default("message_rate_per_sec", 1)
        self._set_default("publish_from_role", "normal")
        self._set_default("high_queue_size", 256)
        self._set_default("medium_queue_size", 512)
        self._set_default("low_queue_size", 32)
        self._set_default("slow_ingress_bandwidth", "1mbit")
        self._set_default("num_messages", 256)
        self._set_default("message_size_bytes", 1024)

    def _set_defaults_s3(self):
        """S3: High queue overflow"""
        self._set_default("num_normal_nodes", 19)
        self._set_default("num_slow_nodes", 1)
        self._set_default("total_peers", 20)
        self._set_default("connect_to", 10)
        self._set_default("gossipsub_d", 6)
        self._set_default("gossipsub_d_high", 8)
        self._set_default("gossipsub_d_low", 4)
        self._set_default("message_rate_per_sec", 2)
        self._set_default("publish_from_role", "normal")
        self._set_default("high_queue_size", 256)
        self._set_default("medium_queue_size", 65536)
        self._set_default("low_queue_size", 65536)
        self._set_default("slow_ingress_bandwidth", "512kbit")
        self._set_default("num_messages", 512)
        self._set_default("message_size_bytes", 1024)

    def _set_defaults_s4_1(self):
        """S4-1: Slow Peer Penalty Decay Parameter Sensitivity"""
        self._set_default("num_normal_nodes", 1)
        self._set_default("num_slow_nodes", 1)
        self._set_default("total_peers", 2)
        self._set_default("connect_to", 1)
        self._set_default("gossipsub_d", 1)
        self._set_default("gossipsub_d_high", 2)
        self._set_default("gossipsub_d_low", 0)
        self._set_default("message_rate_per_sec", 4)
        self._set_default("publish_from_role", "normal")
        self._set_default("high_queue_size", 65536)
        self._set_default("medium_queue_size", 32)
        self._set_default("low_queue_size", 65536)
        self._set_default("slow_ingress_bandwidth", "512kbit")
        self._set_default("num_messages", 1800)
        self._set_default("message_size_bytes", 262144)

    def _set_defaults_s4_2(self):
        """S4-2: Slow Peer Penalty Weight and Burst Sensitivity"""
        self._set_default("num_normal_nodes", 1)
        self._set_default("num_slow_nodes", 1)
        self._set_default("total_peers", 2)
        self._set_default("connect_to", 1)
        self._set_default("gossipsub_d", 1)
        self._set_default("gossipsub_d_high", 2)
        self._set_default("gossipsub_d_low", 0)
        self._set_default("high_queue_size", 65536)
        self._set_default("medium_queue_size", 32)
        self._set_default("low_queue_size", 65536)
        self._set_default("slow_ingress_bandwidth", "512kbit")
        self._set_default("slow_peer_penalty_weight", -0.05)
        # Dual publisher mode
        self._set_default("use_dual_publishers", True)
        # Background: 0.2 msg/s, 1KB from both normal and slow peers
        self._set_default("background_message_size_bytes", 1024)
        self._set_default("background_rate_per_sec", 0.2)
        self._set_default("background_targets", "both")
        # Bursts: 128 msg/s, 128KB, 512 messages from normal peer only
        self._set_default("burst_message_size_bytes", 131072)
        self._set_default("burst_rate_per_sec", 128.0)
        self._set_default("burst_size", 512)
        self._set_default("burst_interval_sec", 120)
        self._set_default("burst_targets", "normal")
        self._set_default("dual_publisher_start_delay_sec", 30)
        self._set_default("run_duration_s", 300)

    def _set_defaults_s5(self):
        """S5: False Slow-Peer from Uplink-Limited Sender"""
        self._set_default("num_normal_nodes", 19)
        self._set_default("num_slow_nodes", 1)
        self._set_default("total_peers", 20)
        self._set_default("connect_to", 10)
        self._set_default("gossipsub_d", 6)
        self._set_default("gossipsub_d_high", 8)
        self._set_default("gossipsub_d_low", 4)
        self._set_default("message_rate_per_sec", 4)
        self._set_default("publish_from_role", "slow")  # Publish from uplink-constrained peer
        self._set_default("high_queue_size", 256)
        self._set_default("medium_queue_size", 512)
        self._set_default("low_queue_size", 1024)
        # Uplink (egress) bandwidth limit on slow peer
        self._set_default("slow_ingress_bandwidth", None)  # No ingress limit
        self._set_default("slow_egress_bandwidth", "512kbit")  # Egress limited
        self._set_default("num_messages", 1800)
        self._set_default("message_size_bytes", 262144)  # 256 KB
        self._set_default("run_duration_s", 600)

    def _get_target_list(self, target_spec: str) -> List[str]:
        """Convert target specification to list of target names."""
        if target_spec == "both" or target_spec == "all":
            return ["normal-nodes", "slow-nodes"]
        elif target_spec == "normal":
            return ["normal-nodes"]
        elif target_spec == "slow":
            return ["slow-nodes"]
        else:
            raise ValueError(f"Unknown target specification: {target_spec}")

    async def _deploy_rbac(self):
        """Deploy RBAC resources for publisher"""
        publisher_builder = PodApiRequesterBuilder().with_namespace(self.namespace)

        role = publisher_builder.build_role()
        rolebinding = publisher_builder.build_rolebinding()

        self.dump_yaml(role, "publisher-role")
        self.dump_yaml(rolebinding, "publisher-rolebinding")
        await self.deploy(deployment=role, wait_for_ready=False)
        await self.deploy(deployment=rolebinding, wait_for_ready=False)

    async def _deploy_scenario(self):
        """Deploy all components"""
        image = Image(repo=self.config.image_repo, tag=self.config.image_tag)

        # RBAC for publisher
        await self._deploy_rbac()

        # 1. Service
        service = self._build_service()
        self.dump_yaml(service, "nimp2p-service")
        await self.deploy(deployment=service, wait_for_ready=False)

        # 2. Deploy both normal and slow nodes simultaneously
        deploy_tasks = []

        if self.config.num_normal_nodes > 0:
            normal_nodes = self._build_normal_nodes(image)
            self.dump_yaml(normal_nodes, "normal-nodes")
            deploy_tasks.append(self.deploy(deployment=normal_nodes, wait_for_ready=True))

        if self.config.num_slow_nodes > 0:
            slow_nodes = self._build_slow_nodes(image)
            self.dump_yaml(slow_nodes, "slow-nodes")
            deploy_tasks.append(self.deploy(deployment=slow_nodes, wait_for_ready=True))

        # Wait for all node deployments to complete
        if deploy_tasks:
            await asyncio.gather(*deploy_tasks)

        # 3. Cold start
        await asyncio.sleep(self.config.delay_cold_start)
        self.log_event("nodes_ready")

        # 4. Publisher deployment
        if self.config.use_dual_publishers:
            await self._deploy_dual_publishers()
        else:
            # Standard single publisher
            configmap = self._build_publisher_configmap()
            self.dump_yaml(configmap, "publisher-config")
            await self.deploy(deployment=configmap, wait_for_ready=False)

            publisher = (
                PodApiRequesterBuilder()
                .with_namespace(self.namespace)
                .with_mode("batch")
                .with_image_override(
                    Image(
                        repo=self.config.publisher_image_repo, tag=self.config.publisher_image_tag
                    )
                )
                .build()
            )
            self.dump_yaml(publisher, "publisher")
            await self.deploy(deployment=publisher, wait_for_ready=False)

            self.log_event("publisher_deployed")

        # 5. Wait
        await asyncio.sleep(self.config.run_duration_s)

    def _build_service(self):
        """Build headless service"""
        return (
            ServiceBuilder()
            .with_name("nimp2p-service")
            .with_namespace(self.namespace)
            .with_cluster_ip("None")
            .with_publish_not_ready_addresses(True)
            .with_selector("app", "zerotenkay")
            .with_port(V1ServicePort(name="p2p-quic", port=5000, target_port=5000, protocol="UDP"))
            .with_port(V1ServicePort(name="p2p-tcp", port=5000, target_port=5000, protocol="TCP"))
            .with_port(V1ServicePort(name="metrics", port=8008, target_port=8008, protocol="TCP"))
            .with_port(V1ServicePort(name="publish", port=8645, target_port=8645, protocol="TCP"))
            .build()
        )

    async def _deploy_dual_publishers(self):
        """
        Deploy two parallel publishers with different traffic patterns:
        1. Background publisher: continuous low-rate traffic
        2. Burst publisher: periodic high-rate bursts (deployed after configurable delay)
        """
        # ConfigMap for background traffic
        background_config = self._build_publisher_configmap(
            config_name="background-config",
            target_spec=self.config.background_targets,
            message_size=self.config.background_message_size_bytes,
            rate=self.config.background_rate_per_sec,
            duration=self.config.run_duration_s,
        )
        self.dump_yaml(background_config, "background-config")
        await self.deploy(deployment=background_config, wait_for_ready=False)

        # ConfigMap for burst traffic
        burst_config = self._build_publisher_configmap(
            config_name="burst-config",
            target_spec=self.config.burst_targets,
            message_size=self.config.burst_message_size_bytes,
            rate=self.config.burst_rate_per_sec,
            burst_size=self.config.burst_size,
            burst_delay=self.config.burst_interval_sec,
            duration=self.config.run_duration_s,
        )
        self.dump_yaml(burst_config, "burst-config")
        await self.deploy(deployment=burst_config, wait_for_ready=False)

        # Deploy background publisher immediately
        background_publisher = (
            PodApiRequesterBuilder()
            .with_namespace(self.namespace)
            .with_name("background-publisher")
            .with_config_map("background-config")
            .with_mode("batch")
            .with_image_override(
                Image(repo=self.config.publisher_image_repo, tag=self.config.publisher_image_tag)
            )
            .build()
        )
        self.dump_yaml(background_publisher, "background-publisher")
        await self.deploy(deployment=background_publisher, wait_for_ready=False)

        self.log_event("dual_publisher_background_deployed")

        # Wait before deploying burst publisher
        await asyncio.sleep(self.config.dual_publisher_start_delay_sec)

        # Deploy burst publisher
        burst_publisher = (
            PodApiRequesterBuilder()
            .with_namespace(self.namespace)
            .with_name("burst-publisher")
            .with_config_map("burst-config")
            .with_mode("batch")
            .with_image_override(
                Image(repo=self.config.publisher_image_repo, tag=self.config.publisher_image_tag)
            )
            .build()
        )
        self.dump_yaml(burst_publisher, "burst-publisher")
        await self.deploy(deployment=burst_publisher, wait_for_ready=False)

        self.log_event("dual_publisher_burst_deployed")

    def _build_normal_nodes(self, image: Image):
        """Normal nodes - no bandwidth limit"""
        builder = Libp2pStatefulSetBuilder()
        builder.with_libp2p_config(
            name="nimp2p", namespace=self.namespace, num_nodes=self.config.num_normal_nodes
        )
        builder.with_image(image)
        builder.with_label("role", "normal")
        builder.with_option(NimLibp2p.peers, self.config.total_peers)
        builder.with_option(NimLibp2p.connect_to, self.config.connect_to)
        builder.with_option(NimLibp2p.muxer, self.config.muxer)
        builder.with_option(NimLibp2p.fragments, "1")
        builder.with_option("SHADOWENV", "false")
        builder.with_option(NimLibp2p.self_trigger, "false")
        builder.with_option(NimLibp2p.service, "nimp2p-service")
        builder.with_option(NimLibp2p.max_connections, "128")
        builder.with_readiness_probe(
            V1Probe(
                tcp_socket=V1TCPSocketAction(port=8645),
                initial_delay_seconds=15,
                period_seconds=10,
                timeout_seconds=5,
                failure_threshold=5,
            )
        )

        # Remove resource limits to allow pod to use resources as needed
        container = find_libp2p_container_config(builder.config)
        container.with_resources(
            V1ResourceRequirements(requests={"memory": "64Mi", "cpu": "150m"}), overwrite=True
        )

        return builder.build()

    def _build_slow_nodes(self, image: Image):
        """Slow nodes - WITH bandwidth limits"""
        builder = Libp2pStatefulSetBuilder()
        builder.with_libp2p_config(
            name="nimp2p-slow", namespace=self.namespace, num_nodes=self.config.num_slow_nodes
        )
        builder.with_image(image)
        builder.with_label("role", "slow")
        builder.with_option(NimLibp2p.peers, self.config.total_peers)
        builder.with_option(NimLibp2p.connect_to, self.config.connect_to)
        builder.with_option(NimLibp2p.muxer, self.config.muxer)
        builder.with_option(NimLibp2p.fragments, "1")
        builder.with_option("SHADOWENV", "false")
        builder.with_option(NimLibp2p.self_trigger, "false")
        builder.with_option(NimLibp2p.service, "nimp2p-service")
        builder.with_option(NimLibp2p.max_connections, "128")
        builder.with_readiness_probe(
            V1Probe(
                tcp_socket=V1TCPSocketAction(port=8645),
                initial_delay_seconds=15,
                period_seconds=10,
                timeout_seconds=5,
                failure_threshold=5,
            )
        )

        # Avoid limits entirely to allow pod to use resources as needed
        container = find_libp2p_container_config(builder.config)
        container.with_resources(
            V1ResourceRequirements(requests={"memory": "128Mi", "cpu": "150m"}), overwrite=True
        )

        # Bandwidth limiting
        builder.with_bandwidth_limit(
            ingress_rate=self.config.slow_ingress_bandwidth,
            egress_rate=self.config.slow_egress_bandwidth,
            burst="32kbit",
        )

        return builder.build()

    def _build_publisher_configmap(
        self,
        config_name: str = "api-requester-config",
        target_spec: str = None,
        message_size: int = None,
        rate: float = None,
        messages: int = None,
        duration: int = None,
        burst_size: int = None,
        burst_delay: int = None,
    ):
        """
        Build ConfigMap for batch publisher.

        Can be used for:
        - Standard single publisher (uses config values)
        - Background traffic (specify target_spec, message_size, rate, duration)
        - Burst traffic (specify target_spec, message_size, rate, burst_size, burst_delay, duration)
        """

        # Use config defaults if not specified
        if target_spec is None:
            target_spec = self.config.publish_from_role
        if message_size is None:
            message_size = self.config.message_size_bytes
        if rate is None:
            rate = self.config.message_rate_per_sec
        if messages is None and duration is None:
            messages = self.config.num_messages

        # Build target list from spec
        target_names = self._get_target_list(target_spec)
        targets = []
        for target_name in target_names:
            if target_name == "normal-nodes" and self.config.num_normal_nodes > 0:
                targets.append(
                    {
                        "name": "normal-nodes",
                        "service": "nimp2p-service",
                        "stateful_set": "nimp2p",
                        "port": 8645,
                    }
                )
            elif target_name == "slow-nodes" and self.config.num_slow_nodes > 0:
                targets.append(
                    {
                        "name": "slow-nodes",
                        "service": "nimp2p-service",
                        "stateful_set": "nimp2p-slow",
                        "port": 8645,
                    }
                )

        # Build load_test config
        load_test_config = {"enabled": True, "rate_per_pod": rate, "parallel_workers": True}

        if duration is not None:
            load_test_config["duration_seconds"] = duration
        if messages is not None:
            load_test_config["messages_per_pod"] = messages
        if burst_size is not None:
            load_test_config["burst_size"] = burst_size
        if burst_delay is not None:
            load_test_config["burst_delay"] = burst_delay

        # Build config dictionary
        config_dict = {
            "targets": targets,
            "endpoints": [
                {
                    "name": "publish",
                    "url": "http://{node}:{port}/publish",
                    "headers": {"Content-Type": "application/json"},
                    "params": {"topic": "test", "msgSize": message_size, "version": 1},
                    "type": "POST",
                    "paged": False,
                }
            ],
            "requests": [
                {"name": "publish-req", "endpoint": "publish", "retries": 0, "retry_delay": 0}
            ],
            "actions": [
                {
                    "name": "publish-action",
                    "requests": ["publish-req"],
                    "targets": target_names,
                    "pod_count": "all",
                    "order": self.config.publish_order,
                    "loop_order": "foreach_pod_make_all_requests",
                    "load_test": load_test_config,
                }
            ],
        }

        return {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": config_name, "namespace": self.namespace},
            "data": {"config.yaml": yaml.dump(config_dict, default_flow_style=False)},
        }
