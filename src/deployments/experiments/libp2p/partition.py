"""Regression scenario: the network forms as two halves that later meet."""

import asyncio
import logging
import time
from typing import ClassVar, List

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
from pydantic import Field, NonNegativeFloat, NonNegativeInt, model_validator

from src.deployments.core.k8s_cleanup import delete_network_policy
from src.deployments.core.k8s_rollout import get_pods_for_statefulset, label_pods
from src.deployments.experiments.libp2p.nimlibp2p import ExpConfig, NimLibp2pExperiment
from src.deployments.registry import experiment

logger = logging.getLogger(__name__)

SIDE_LABEL = "partition-side"
NAMESPACE_NAME_LABEL = "kubernetes.io/metadata.name"


class PartitionConfig(ExpConfig):
    partition_fraction: float = Field(default=0.5, gt=0, lt=1)
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

    @model_validator(mode="after")
    def _check_both_sides_populated(self):
        split = int(self.num_relay_nodes * self.partition_fraction)
        if split < 1 or split >= self.num_relay_nodes:
            raise ValueError(
                f"partition_fraction {self.partition_fraction} of {self.num_relay_nodes} nodes "
                f"puts {split} on one side, so the run would report success without a split"
            )
        return self


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

    Egress reuses the ingress allow-list rather than denying outright, or the nodes lose
    DNS. The label must be one we set: the CNI does not enforce policies selecting on
    per-pod-unique labels. Both directions are restricted because a partition stops traffic
    both ways; whether ingress alone would contain quic is not settled, see PR discussion.
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
    post_run_analysis: ClassVar[str] = "src.analysis.post_run.partition:run_partition_analysis"

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
            raise ValueError(
                f"partition_fraction {self.config.partition_fraction} leaves one side empty "
                f"at {nodes.spec.replicas} nodes; there would be no split to measure"
            )

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
            delete_network_policy(name, self.namespace, self.api_client)
        self.log_event("partition_healed")
