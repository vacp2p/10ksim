"""Adverse-condition regression scenarios: degraded links, node churn, network partition.

Each one reuses the nimlibp2p regression experiment and only changes what the network
does to it, so delivery, latency and mesh health stay comparable to a plain run.
"""

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
    """Regression run over a high-latency, jittery, lossy link.

    Exercises the timeout, retransmit and gossip-repair paths that a clean link never
    reaches. Latency is shaped, so read delivery and mesh health rather than absolute
    latency, and compare against another run of the same profile.
    """

    config: DegradedConfig


class ChurnConfig(ExpConfig):
    churn_fraction: NonNegativeFloat = 0.2
    """Share of relay nodes taken down mid-run, from the highest ordinals."""
    churn_at: NonNegativeInt = 30
    """Seconds after the first message before taking them down."""
    churn_downtime: NonNegativeInt = 60
    """Seconds to stay down before rejoining."""
    churn_rejoin_timeout: NonNegativeInt = 600


def churn_targets(nodes: V1StatefulSet, fraction: float) -> List[str]:
    """Highest-ordinal pod names, which is what a scale-down removes."""
    replicas = nodes.spec.replicas
    count = int(replicas * fraction)
    return [f"{nodes.metadata.name}-{i}" for i in range(replicas - count, replicas)]


@experiment(name="nimlibp2p-churn")
class NodeChurn(NimLibp2pExperiment):
    """Regression run where a share of the nodes drop out mid-run and rejoin.

    Scaling the StatefulSet down holds them down for `churn_downtime`; deleting the
    pods would not, because the controller replaces each one within seconds and the
    network would only ever lose a trickle at a time. They come back with the same
    names and have to rediscover peers, which exercises peer management, reconnection
    and mesh repair. Delivery should recover; messages published into the gap may not
    reach the nodes that were down for it.
    """

    config: ChurnConfig

    def _publishable_nodes(self) -> int:
        """Keep the publisher off the churned nodes.

        They come back on new addresses, and the publisher connects to the address it
        looked up, so publishing to one that has just been replaced hangs until the
        request times out. That is our harness tripping over the scenario rather than
        anything about the protocol, and it starves the run of published messages.
        """
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
    """Share of relay nodes on the first side of the split."""
    heal_at: NonNegativeInt = 120
    """Seconds after the first message before the two halves are allowed to meet."""
    node_start_delay: NonNegativeInt = 240
    """Must outlast pod creation: the halves are labelled once every pod exists, and a
    node that dialled before its label was on would sit across the split and stay there."""
    wait_nodes_ready: bool = False
    """Readiness here means the node already has a healthy mesh, which is exactly what we
    need to get in front of, so the split is set up on existence instead."""
    delay_cold_start: NonNegativeFloat = 700
    """Long enough to cover pod creation, the start delay above, and each half meshing."""
    bootstrap_nodes: NonNegativeInt = 1
    """One shared anchor, left unlabelled so both halves can reach it. It is the only
    rendezvous through which they can learn each other's addresses, and it cannot carry
    traffic between them: the bootstrap role returns before GossipSub is mounted, so it
    answers DHT queries and nothing else. Give each half its own anchor and neither ever
    hears of the other, which makes a merge impossible rather than merely slow."""


SIDE_LABEL = "partition-side"
NAMESPACE_NAME_LABEL = "kubernetes.io/metadata.name"


def partition_sides(nodes: V1StatefulSet, fraction: float) -> tuple[List[str], List[str]]:
    replicas = nodes.spec.replicas
    split = int(replicas * fraction)
    names = [f"{nodes.metadata.name}-{i}" for i in range(replicas)]
    return names[:split], names[split:]


def _not_far_side(namespace: str, far_side: str) -> List[V1NetworkPolicyPeer]:
    """Everything except the far side: same-namespace pods that are not on it, plus any
    other namespace. Unlabelled pods match `NotIn`, so the publisher stays reachable, and
    allowing other namespaces keeps DNS and metrics scraping working through the split."""
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
    """Cut pods labelled `side` off from pods labelled `far_side`, both directions.

    Restricting ingress alone is not enough. It stops a TCP handshake, because the reply
    never comes back, which makes a TCP probe look reassuringly blocked. quic is UDP and
    goes straight through: with an ingress-only policy the halves kept delivering to each
    other in single-digit milliseconds while a TCP probe to the same pods timed out. So
    both directions are restricted, and the two policies are applied to both sides.

    Egress needs the same allow-list as ingress rather than a blanket deny, or the nodes
    lose DNS and never resolve the bootstrap service at all.

    The side label is one we set ourselves rather than a per-pod identifier like
    `statefulset.kubernetes.io/pod-name`: the CNI does not give per-pod-unique labels a
    security identity, so a policy selecting on one is accepted and then never enforced.
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

    The split is in place before the nodes dial, so each half discovers and meshes only
    within itself, and the two are allowed to meet part way through publishing. What it
    measures is convergence: how fast the halves merge and whether delivery returns to
    everyone once they do.

    It is deliberately not a cut of a live mesh. A policy only decides whether a
    connection may be opened, so adding one to an already-meshed network leaves every
    existing link running and changes nothing (measured: delivery, latency and peer
    counts all unmoved). Cutting live connections needs packet-level drops instead.
    """

    config: PartitionConfig

    async def _wait_for_pods_to_exist(self, nodes: V1StatefulSet, timeout: int = 600) -> None:
        """Existence, not readiness: a node is only Ready once it has a healthy mesh, and
        the split has to be in place well before that."""
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
