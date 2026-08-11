"""Checks that a scenario's disturbance actually happened.

A scenario whose disturbance silently did not apply still produces a clean-looking run:
the partition that never split reads as "the halves stayed connected", and the link that
was never shaped reads as "the degradation had no effect". These turn that into a result
the run reports rather than something read off a dashboard by hand at the right moment.
"""

import logging
from typing import List

from kubernetes import client
from kubernetes.client import ApiException

from src.deployments.core.k8s_rollout import get_pods_for_statefulset

logger = logging.getLogger(__name__)

SHAPING_CONTAINER = "slowyourroll"


class DisturbanceNotApplied(Exception):
    """The scenario's disturbance did not take effect, so the run measures nothing."""


def check_shaping_applied(name: str, namespace: str, api_client=None) -> int:
    """Every pod ran the netem init container to completion. Returns the pod count.

    The qdisc is added by an init container, so a pod whose init container failed carries
    an unshaped link while looking healthy.
    """
    pods = list(get_pods_for_statefulset(name, namespace, api_client))
    if not pods:
        raise DisturbanceNotApplied(f"No pods found for `{namespace}/{name}` to check shaping on")

    unshaped = []
    for pod in pods:
        statuses = [
            s for s in (pod.status.init_container_statuses or []) if s.name == SHAPING_CONTAINER
        ]
        if not statuses:
            unshaped.append(f"{pod.metadata.name} (no {SHAPING_CONTAINER} container)")
            continue
        terminated = statuses[0].state.terminated if statuses[0].state else None
        if terminated is None or terminated.exit_code != 0:
            code = "still running" if terminated is None else f"exit {terminated.exit_code}"
            unshaped.append(f"{pod.metadata.name} ({code})")

    if unshaped:
        raise DisturbanceNotApplied(
            f"{len(unshaped)} of {len(pods)} pods are not shaped: {unshaped[:5]}"
        )

    logger.info(f"Shaping applied on all {len(pods)} pods")
    return len(pods)


def check_partition_applied(policy_names: List[str], namespace: str, api_client=None) -> None:
    """The policies reached the API and cut both directions.

    Ingress alone stops a TCP handshake but not quic's UDP, which is how a run once
    reported a split that had been delivering across itself the whole time.
    """
    api = client.NetworkingV1Api(api_client or client.ApiClient())
    for policy_name in policy_names:
        try:
            policy = api.read_namespaced_network_policy(name=policy_name, namespace=namespace)
        except ApiException as e:
            raise DisturbanceNotApplied(
                f"NetworkPolicy `{namespace}/{policy_name}` is not in the API: {e.status}"
            ) from e

        missing = {"Ingress", "Egress"} - set(policy.spec.policy_types or [])
        if missing:
            raise DisturbanceNotApplied(
                f"NetworkPolicy `{policy_name}` does not restrict {sorted(missing)}, so the "
                f"halves can still reach each other"
            )

    logger.info(f"Partition applied: {policy_names} restrict both directions")


def check_nodes_left(name: str, namespace: str, expected: int, api_client=None) -> None:
    """The churned pods are actually gone, not just requested to go."""
    remaining = len(list(get_pods_for_statefulset(name, namespace, api_client)))
    if remaining != expected:
        raise DisturbanceNotApplied(
            f"Churn left {remaining} pods running, expected {expected}; the nodes never went down"
        )
    logger.info(f"Churn took effect: {remaining} pods remain")
