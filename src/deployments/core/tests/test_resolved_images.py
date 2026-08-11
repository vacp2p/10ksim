import logging
from unittest.mock import MagicMock

from kubernetes.client.rest import ApiException

from src.deployments.core import k8s_rollout
from src.deployments.core.k8s_rollout import resolved_images

DIGEST = "docker.io/radiken/dst-test-node@sha256:" + "a" * 64
OTHER = "docker.io/radiken/dst-test-node@sha256:" + "b" * 64


def _container(name, image_id):
    # `name` is a MagicMock constructor kwarg, so it has to be set after construction.
    status = MagicMock(image_id=image_id)
    status.name = name
    return status


def _pod(*containers):
    pod = MagicMock()
    pod.status.container_statuses = [_container(name, image_id) for name, image_id in containers]
    return pod


def test_reports_the_digest_the_pods_pulled(mocker):
    mocker.patch.object(
        k8s_rollout, "get_pods_for_statefulset", return_value=[_pod(("libp2p-node", DIGEST))] * 3
    )
    assert resolved_images("pod", "zerotesting") == {"libp2p-node": [DIGEST]}


def test_a_split_rollout_reports_both_digests(mocker):
    """One mutable tag can resolve differently per pod; a single value would hide that."""
    mocker.patch.object(
        k8s_rollout,
        "get_pods_for_statefulset",
        return_value=[_pod(("libp2p-node", DIGEST)), _pod(("libp2p-node", OTHER))],
    )
    assert resolved_images("pod", "zerotesting") == {"libp2p-node": [DIGEST, OTHER]}


def test_containers_are_reported_separately(mocker):
    mocker.patch.object(
        k8s_rollout,
        "get_pods_for_statefulset",
        return_value=[_pod(("libp2p-node", DIGEST), ("sidecar", OTHER))],
    )
    assert resolved_images("pod", "zerotesting") == {"libp2p-node": [DIGEST], "sidecar": [OTHER]}


def test_pods_that_have_not_pulled_yet_are_skipped(mocker):
    mocker.patch.object(
        k8s_rollout, "get_pods_for_statefulset", return_value=[_pod(("libp2p-node", ""))]
    )
    assert resolved_images("pod", "zerotesting") == {}


def test_an_api_error_does_not_take_the_run_down(mocker, caplog):
    """Recording which binary ran is worth a warning, not a failed experiment."""
    mocker.patch.object(
        k8s_rollout, "get_pods_for_statefulset", side_effect=ApiException(status=403)
    )
    with caplog.at_level(logging.WARNING):
        assert resolved_images("pod", "zerotesting") == {}
    assert "Could not resolve images" in caplog.text
