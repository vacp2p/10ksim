import logging
from unittest.mock import MagicMock

from kubernetes.client.rest import ApiException

from src.deployments.core import pod_logs
from src.deployments.core.pod_logs import capture_pod_logs


def _api(pod_names, *, logs=None, list_error=None, read_error=None):
    api = MagicMock()
    if list_error:
        api.list_namespaced_pod.side_effect = list_error
    else:
        pods = []
        for name in pod_names:
            pod = MagicMock()
            pod.metadata.name = name
            pods.append(pod)
        api.list_namespaced_pod.return_value = MagicMock(items=pods)
    if read_error:
        api.read_namespaced_pod_log.side_effect = read_error
    else:
        api.read_namespaced_pod_log.side_effect = lambda name, namespace: (logs or {}).get(
            name, f"log for {name}"
        )
    return api


def test_writes_one_file_per_pod(mocker, tmp_path):
    mocker.patch.object(pod_logs.client, "CoreV1Api", return_value=_api(["pod-0", "pod-1"]))
    assert capture_pod_logs("ns", tmp_path) == 2
    assert (tmp_path / "pod-0.log").read_text() == "log for pod-0"
    assert (tmp_path / "pod-1.log").read_text() == "log for pod-1"


def test_one_unreadable_pod_does_not_lose_the_rest(mocker, tmp_path, caplog):
    api = _api(["pod-0", "pod-1"])
    api.read_namespaced_pod_log.side_effect = lambda name, namespace: (
        (_ for _ in ()).throw(ApiException(status=400)) if name == "pod-0" else "ok"
    )
    mocker.patch.object(pod_logs.client, "CoreV1Api", return_value=api)
    with caplog.at_level(logging.WARNING):
        assert capture_pod_logs("ns", tmp_path) == 1
    assert (tmp_path / "pod-1.log").exists()
    assert "Could not read logs from pod `pod-0`" in caplog.text


def test_a_listing_failure_is_not_fatal(mocker, tmp_path, caplog):
    """The capture is a fallback; losing it must not take the run down with it."""
    mocker.patch.object(
        pod_logs.client, "CoreV1Api", return_value=_api([], list_error=ApiException(status=403))
    )
    with caplog.at_level(logging.WARNING):
        assert capture_pod_logs("ns", tmp_path) == 0
    assert "Could not list pods" in caplog.text


def test_the_destination_is_created(mocker, tmp_path):
    mocker.patch.object(pod_logs.client, "CoreV1Api", return_value=_api(["pod-0"]))
    dest = tmp_path / "nested" / "kubectl_logs"
    assert capture_pod_logs("ns", dest) == 1
    assert dest.is_dir()
