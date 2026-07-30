"""Adverse-condition regression scenarios: degraded links, node churn, network partition."""

import asyncio
import logging
import time
from typing import List

from kubernetes.client import (
    V1LabelSelector,
    V1LabelSelectorRequirement,
    V1NetworkPolicy,
    V1NetworkPolicyEgressRule,
    V1NetworkPolicyIngressRule,
    V1NetworkPolicyPeer,
    V1NetworkPolicySpec,
    V1ObjectMeta,
    V1StatefulSet,
)
from pydantic import NonNegativeFloat, NonNegativeInt

from src.deployments.core.k8s_cleanup import delete_network_policy
from src.deployments.core.k8s_rollout import (
    get_pods_for_statefulset,
    label_pods,
    scale_statefulset,
    wait_for_rollout,
)
from src.deployments.experiments.libp2p.nimlibp2p import ExpConfig, NimLibp2pExperiment
from src.deployments.registry import experiment

logger = logging.getLogger(__name__)


class DegradedConfig(ExpConfig):
    network_delay: NonNegativeInt = 200
    network_jitter: NonNegativeInt = 50
    network_loss_pct: NonNegativeFloat = 1


@experiment(name="nimlibp2p-degraded")
class DegradedNetwork(NimLibp2pExperiment):
    """Regression run over a high-latency, jittery, lossy link."""

    config: DegradedConfig


class ChurnConfig(ExpConfig):
    churn_fraction: NonNegativeFloat = 0.2
    """Share taken down, from the highest ordinals."""
    churn_at: NonNegativeInt = 30
    """Seconds after the first message."""
    churn_downtime: NonNegativeInt = 60
    churn_rejoin_timeout: NonNegativeInt = 600


def churn_targets(nodes: V1StatefulSet, fraction: float) -> List[str]:
    """Highest-ordinal pods, which is what a scale-down removes."""
    replicas = nodes.spec.replicas
    count = int(replicas * fraction)
    return [f"{nodes.metadata.name}-{i}" for i in range(replicas - count, replicas)]


@experiment(name="nimlibp2p-churn")
class NodeChurn(NimLibp2pExperiment):
    """Regression run where a share of the nodes drop out mid-run and rejoin.

    Scale down rather than delete: a deleted pod is replaced within seconds.
    """

    config: ChurnConfig

    def _publishable_nodes(self) -> int:
        """Churned nodes return on new addresses; publishing to a stale one hangs."""
        churned = int(self.config.num_relay_nodes * self.config.churn_fraction)
        return self.config.num_relay_nodes - churned

    async def _mid_run(self, nodes: V1StatefulSet) -> None:
        await asyncio.sleep(self.config.churn_at)

        targets = churn_targets(nodes, self.config.churn_fraction)
        if not targets:
            logger.warning(f"churn_fraction {self.config.churn_fraction} takes down no nodes")
            return

        replicas = nodes.spec.replicas
        name = nodes.metadata.name
        self.log_event({"event": "churn_down", "nodes": targets})
        logger.info(f"Taking down {len(targets)} nodes: {targets[0]}..{targets[-1]}")
        scale_statefulset(name, self.namespace, replicas - len(targets), self.api_client)
        self.log_event({"event": "churn_is_down", "nodes": targets})

        await asyncio.sleep(self.config.churn_downtime)

        self.log_event({"event": "churn_rejoin", "nodes": targets})
        scale_statefulset(name, self.namespace, replicas, self.api_client)
        await wait_for_rollout(nodes, self.api_client, timeout=self.config.churn_rejoin_timeout)
        self.log_event({"event": "churn_rejoined", "nodes": targets})


class PartitionConfig(ExpConfig):
    partition_fraction: NonNegativeFloat = 0.5
    """Share of relay nodes on the first side."""
    heal_at: NonNegativeInt = 120
    """Seconds after the first message before the halves may meet."""
    node_start_delay: NonNegativeInt = 240
    """Must outlast pod creation, or a node dials before its side label is on."""
    wait_nodes_ready: bool = False
    """Ready means already meshed, which the split has to precede."""
    delay_cold_start: NonNegativeFloat = 700
    """Must cover each half meshing, slow behind a split: 7 min at 30 nodes. Publishing
    before both halves converge invalidates the run."""
    bootstrap_nodes: NonNegativeInt = 1
    """One shared unlabelled anchor, the only way the halves learn each other's addresses.
    It cannot relay: the bootstrap role returns before GossipSub is mounted."""


SIDE_LABEL = "partition-side"
NAMESPACE_NAME_LABEL = "kubernetes.io/metadata.name"


def partition_sides(nodes: V1StatefulSet, fraction: float) -> tuple[List[str], List[str]]:
    replicas = nodes.spec.replicas
    split = int(replicas * fraction)
    names = [f"{nodes.metadata.name}-{i}" for i in range(replicas)]
    return names[:split], names[split:]


def _not_far_side(namespace: str, far_side: str) -> List[V1NetworkPolicyPeer]:
    """Unlabelled pods match `NotIn` so the publisher stays reachable; other namespaces
    keep DNS and metrics working."""
    return [
        V1NetworkPolicyPeer(
            pod_selector=V1LabelSelector(
                match_expressions=[
                    V1LabelSelectorRequirement(key=SIDE_LABEL, operator="NotIn", values=[far_side])
                ]
            )
        ),
        V1NetworkPolicyPeer(
            namespace_selector=V1LabelSelector(
                match_expressions=[
                    V1LabelSelectorRequirement(
                        key=NAMESPACE_NAME_LABEL, operator="NotIn", values=[namespace]
                    )
                ]
            )
        ),
    ]


def build_partition_policy(name: str, namespace: str, side: str, far_side: str) -> V1NetworkPolicy:
    """Cut `side` off from `far_side`, both directions.

    Ingress alone only stops TCP; quic is UDP and goes straight through. Egress reuses the
    ingress allow-list, or the nodes lose DNS. The label must be one we set: the CNI does
    not enforce policies selecting on per-pod-unique labels.
    """
    peers = _not_far_side(namespace, far_side)
    return V1NetworkPolicy(
        api_version="networking.k8s.io/v1",
        kind="NetworkPolicy",
        metadata=V1ObjectMeta(name=name, namespace=namespace),
        spec=V1NetworkPolicySpec(
            policy_types=["Ingress", "Egress"],
            pod_selector=V1LabelSelector(match_labels={SIDE_LABEL: side}),
            ingress=[V1NetworkPolicyIngressRule(_from=peers)],
            egress=[V1NetworkPolicyEgressRule(to=peers)],
        ),
    )


@experiment(name="nimlibp2p-partition")
class NetworkPartition(NimLibp2pExperiment):
    """Regression run where the network forms as two halves that later meet.

    Measures convergence, not a live cut: a policy only gates opening a connection.
    """

    config: PartitionConfig

    async def _wait_for_pods_to_exist(self, nodes: V1StatefulSet, timeout: int = 600) -> None:
        """Existence, not readiness: Ready already means meshed."""
        name, wanted = nodes.metadata.name, nodes.spec.replicas
        deadline = time.monotonic() + timeout
        while True:
            found = len(list(get_pods_for_statefulset(name, self.namespace, self.api_client)))
            if found >= wanted:
                logger.info(f"All {wanted} pods exist; labelling the split")
                return
            if time.monotonic() > deadline:
                raise TimeoutError(f"Only {found}/{wanted} pods exist after {timeout}s")
            await asyncio.sleep(5)

    async def _after_nodes(self, nodes: V1StatefulSet) -> None:
        side_a, side_b = partition_sides(nodes, self.config.partition_fraction)
        if not side_a or not side_b:
            logger.warning(
                f"partition_fraction {self.config.partition_fraction} leaves one side empty"
            )
            return

        await self._wait_for_pods_to_exist(nodes)
        labelled = label_pods(side_a, self.namespace, {SIDE_LABEL: "a"}, self.api_client)
        labelled += label_pods(side_b, self.namespace, {SIDE_LABEL: "b"}, self.api_client)
        self.log_event({"event": "partition_labelled", "pods": labelled})
        if labelled != len(side_a) + len(side_b):
            raise RuntimeError(
                f"Labelled {labelled} of {len(side_a) + len(side_b)} pods; an unlabelled pod "
                "is not covered by the split and would bridge the two halves."
            )

        policies = [
            build_partition_policy("partition-a", self.namespace, "a", "b"),
            build_partition_policy("partition-b", self.namespace, "b", "a"),
        ]
        for policy in policies:
            self.dump_yaml(policy, policy.metadata.name)
        await self.deploy(deployment=policies, wait_for_ready=False)
        self.log_event({"event": "partition_applied", "side_a": len(side_a), "side_b": len(side_b)})

    async def _mid_run(self, nodes: V1StatefulSet) -> None:
        await asyncio.sleep(self.config.heal_at)

        self.log_event("partition_heal")
        for name in ("partition-a", "partition-b"):
            delete_network_policy(name, self.namespace)
        self.log_event("partition_healed")
