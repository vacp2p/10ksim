"""Adverse-condition regression scenarios: degraded links, node churn, network partition.

Each one reuses the nimlibp2p regression experiment and only changes what the network
does to it, so delivery, latency and mesh health stay comparable to a plain run.
"""

import asyncio
import logging
from typing import List

from kubernetes.client import (
    V1LabelSelector,
    V1LabelSelectorRequirement,
    V1NetworkPolicy,
    V1NetworkPolicyIngressRule,
    V1NetworkPolicyPeer,
    V1NetworkPolicySpec,
    V1ObjectMeta,
    V1StatefulSet,
)
from pydantic import NonNegativeFloat, NonNegativeInt

from src.deployments.core.k8s_cleanup import delete_network_policy, delete_pod
from src.deployments.core.k8s_rollout import wait_for_rollout
from src.deployments.experiments.libp2p.nimlibp2p import ExpConfig, NimLibp2pExperiment
from src.deployments.registry import experiment

logger = logging.getLogger(__name__)


class DegradedConfig(ExpConfig):
    network_delay: NonNegativeInt = 200
    network_jitter: NonNegativeInt = 50
    network_loss_pct: NonNegativeFloat = 1


@experiment(name="nimlibp2p-degraded")
class DegradedNetwork(NimLibp2pExperiment):
    """Regression run over a high-latency, jittery, lossy link.

    Exercises the timeout, retransmit and gossip-repair paths that a clean link never
    reaches. Latency is shaped, so read delivery and mesh health rather than absolute
    latency, and compare against another run of the same profile.
    """

    config: DegradedConfig


class ChurnConfig(ExpConfig):
    churn_fraction: NonNegativeFloat = 0.2
    """Share of relay nodes killed mid-run, taken from the highest ordinals."""
    churn_at: NonNegativeInt = 30
    """Seconds after the first message before killing."""
    churn_rejoin_timeout: NonNegativeInt = 600


def churn_targets(nodes: V1StatefulSet, fraction: float) -> List[str]:
    """Highest-ordinal pod names to kill, deterministic so runs stay comparable."""
    replicas = nodes.spec.replicas
    count = int(replicas * fraction)
    return [f"{nodes.metadata.name}-{i}" for i in range(replicas - count, replicas)]


@experiment(name="nimlibp2p-churn")
class NodeChurn(NimLibp2pExperiment):
    """Regression run where a share of the nodes are killed mid-run and rejoin.

    The StatefulSet recreates them, so they come back with the same names and have to
    rediscover peers. Exercises peer management, reconnection and mesh repair
    (prune/graft). Delivery should recover; messages published into the gap may not
    reach the nodes that were down for it.
    """

    config: ChurnConfig

    async def _mid_run(self, nodes: V1StatefulSet) -> None:
        await asyncio.sleep(self.config.churn_at)

        targets = churn_targets(nodes, self.config.churn_fraction)
        if not targets:
            logger.warning(f"churn_fraction {self.config.churn_fraction} kills no nodes")
            return

        self.log_event({"event": "churn_kill", "nodes": targets})
        logger.info(f"Killing {len(targets)} nodes: {targets}")
        for name in targets:
            delete_pod(name, self.namespace)
        self.log_event({"event": "churn_killed", "nodes": targets})

        await wait_for_rollout(nodes, self.api_client, timeout=self.config.churn_rejoin_timeout)
        self.log_event({"event": "churn_rejoined", "nodes": targets})


class PartitionConfig(ExpConfig):
    partition_fraction: NonNegativeFloat = 0.5
    """Share of relay nodes on the smaller side of the split."""
    partition_at: NonNegativeInt = 30
    """Seconds after the first message before splitting."""
    partition_duration: NonNegativeInt = 60
    """Seconds to hold the split before healing."""


POD_NAME_LABEL = "statefulset.kubernetes.io/pod-name"
NAMESPACE_NAME_LABEL = "kubernetes.io/metadata.name"


def partition_sides(nodes: V1StatefulSet, fraction: float) -> tuple[List[str], List[str]]:
    replicas = nodes.spec.replicas
    split = int(replicas * fraction)
    names = [f"{nodes.metadata.name}-{i}" for i in range(replicas)]
    return names[:split], names[split:]


def build_partition_policy(
    name: str, namespace: str, side: List[str], far_side: List[str]
) -> V1NetworkPolicy:
    """Deny `side` any ingress from `far_side`, leaving every other source alone.

    Applied to both sides so the split is bidirectional. Only ingress is restricted, so
    DNS and other egress still work. Pods without the ordinal label (publisher,
    bootstrap) match `NotIn` and stay reachable, as do other namespaces, which keeps
    metrics scraping alive through the split.
    """
    return V1NetworkPolicy(
        api_version="networking.k8s.io/v1",
        kind="NetworkPolicy",
        metadata=V1ObjectMeta(name=name, namespace=namespace),
        spec=V1NetworkPolicySpec(
            policy_types=["Ingress"],
            pod_selector=V1LabelSelector(
                match_expressions=[
                    V1LabelSelectorRequirement(key=POD_NAME_LABEL, operator="In", values=side)
                ]
            ),
            ingress=[
                V1NetworkPolicyIngressRule(
                    _from=[
                        V1NetworkPolicyPeer(
                            pod_selector=V1LabelSelector(
                                match_expressions=[
                                    V1LabelSelectorRequirement(
                                        key=POD_NAME_LABEL, operator="NotIn", values=far_side
                                    )
                                ]
                            )
                        ),
                        V1NetworkPolicyPeer(
                            namespace_selector=V1LabelSelector(
                                match_expressions=[
                                    V1LabelSelectorRequirement(
                                        key=NAMESPACE_NAME_LABEL,
                                        operator="NotIn",
                                        values=[namespace],
                                    )
                                ]
                            )
                        ),
                    ]
                )
            ],
        ),
    )


@experiment(name="nimlibp2p-partition")
class NetworkPartition(NimLibp2pExperiment):
    """Regression run split into two halves mid-run, then healed.

    Tests whether the mesh reconverges and delivery recovers once the split lifts.
    Messages published while split should only reach the publisher's own side, so
    expect a delivery dip over the split window and full delivery after it.
    """

    config: PartitionConfig

    async def _mid_run(self, nodes: V1StatefulSet) -> None:
        await asyncio.sleep(self.config.partition_at)

        side_a, side_b = partition_sides(nodes, self.config.partition_fraction)
        if not side_a or not side_b:
            logger.warning(
                f"partition_fraction {self.config.partition_fraction} leaves one side empty"
            )
            return

        policies = [
            build_partition_policy("partition-a", self.namespace, side_a, side_b),
            build_partition_policy("partition-b", self.namespace, side_b, side_a),
        ]
        for policy in policies:
            self.dump_yaml(policy, policy.metadata.name)

        self.log_event({"event": "partition_apply", "side_a": side_a, "side_b": side_b})
        await self.deploy(deployment=policies, wait_for_ready=False)
        self.log_event("partition_applied")

        await asyncio.sleep(self.config.partition_duration)

        self.log_event("partition_heal")
        for policy in policies:
            delete_network_policy(policy.metadata.name, self.namespace)
        self.log_event("partition_healed")
