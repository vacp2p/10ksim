from unittest.mock import MagicMock

import pytest
from kubernetes.client.rest import ApiException

from src.deployments.experiments.libp2p import disturbance
from src.deployments.experiments.libp2p.disturbance import (
    DisturbanceNotApplied,
    check_nodes_left,
    check_partition_applied,
    check_shaping_applied,
)


def _pod(name, *, shaped=True, exit_code=0, running=False):
    pod = MagicMock()
    pod.metadata.name = name
    if not shaped:
        pod.status.init_container_statuses = []
        return pod
    status = MagicMock()
    status.name = disturbance.SHAPING_CONTAINER
    status.state.terminated = None if running else MagicMock(exit_code=exit_code)
    pod.status.init_container_statuses = [status]
    return pod


def _policy(policy_types):
    policy = MagicMock()
    policy.spec.policy_types = policy_types
    return policy


class TestShaping:
    def test_passes_when_every_pod_ran_the_qdisc(self, mocker):
        mocker.patch.object(
            disturbance, "get_pods_for_statefulset", return_value=[_pod("pod-0"), _pod("pod-1")]
        )
        assert check_shaping_applied("pod", "ns") == 2

    def test_a_failed_init_container_means_an_unshaped_link(self, mocker):
        mocker.patch.object(
            disturbance,
            "get_pods_for_statefulset",
            return_value=[_pod("pod-0"), _pod("pod-1", exit_code=1)],
        )
        with pytest.raises(DisturbanceNotApplied, match="pod-1"):
            check_shaping_applied("pod", "ns")

    def test_a_pod_with_no_shaping_container_is_caught(self, mocker):
        mocker.patch.object(
            disturbance, "get_pods_for_statefulset", return_value=[_pod("pod-0", shaped=False)]
        )
        with pytest.raises(DisturbanceNotApplied, match="no slowyourroll"):
            check_shaping_applied("pod", "ns")

    def test_no_pods_at_all_is_a_failure_not_a_pass(self, mocker):
        """An empty list would otherwise satisfy "every pod is shaped"."""
        mocker.patch.object(disturbance, "get_pods_for_statefulset", return_value=[])
        with pytest.raises(DisturbanceNotApplied, match="No pods found"):
            check_shaping_applied("pod", "ns")


class TestPartition:
    def test_passes_when_both_directions_are_cut(self, mocker):
        api = MagicMock()
        api.read_namespaced_network_policy.return_value = _policy(["Ingress", "Egress"])
        mocker.patch.object(disturbance.client, "NetworkingV1Api", return_value=api)
        check_partition_applied(["partition-a", "partition-b"], "ns")
        assert api.read_namespaced_network_policy.call_count == 2

    def test_ingress_only_does_not_contain_quic(self, mocker):
        """A TCP probe looked reassuring while the halves delivered to each other over UDP."""
        api = MagicMock()
        api.read_namespaced_network_policy.return_value = _policy(["Ingress"])
        mocker.patch.object(disturbance.client, "NetworkingV1Api", return_value=api)
        with pytest.raises(DisturbanceNotApplied, match="Egress"):
            check_partition_applied(["partition-a"], "ns")

    def test_a_policy_that_never_reached_the_api_is_caught(self, mocker):
        api = MagicMock()
        api.read_namespaced_network_policy.side_effect = ApiException(status=404)
        mocker.patch.object(disturbance.client, "NetworkingV1Api", return_value=api)
        with pytest.raises(DisturbanceNotApplied, match="not in the API"):
            check_partition_applied(["partition-a"], "ns")


class TestChurn:
    def test_passes_when_the_pods_are_gone(self, mocker):
        mocker.patch.object(
            disturbance,
            "get_pods_for_statefulset",
            return_value=[_pod(f"pod-{i}") for i in range(8)],
        )
        check_nodes_left("pod", "ns", 8)

    def test_pods_that_never_went_down_are_caught(self, mocker):
        mocker.patch.object(
            disturbance,
            "get_pods_for_statefulset",
            return_value=[_pod(f"pod-{i}") for i in range(10)],
        )
        with pytest.raises(DisturbanceNotApplied, match="left 10 pods"):
            check_nodes_left("pod", "ns", 8)
