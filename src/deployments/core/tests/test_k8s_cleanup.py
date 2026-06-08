from unittest.mock import MagicMock

import pytest
from kubernetes.client.rest import ApiException

from src.deployments.core import k8s_cleanup
from src.deployments.core.k8s_cleanup import (
    cleanup_resources,
    poll_namespace_has_objects,
    wait_for_no_objs_in_namespace,
)


def _list_result(items):
    r = MagicMock()
    r.items = items
    return r


# --------------------------------------------------------------------------- #
# poll_namespace_has_objects  (lists resources via k8s client)
# --------------------------------------------------------------------------- #
class TestPollNamespaceHasObjects:
    def _patch_apis(self, mocker, *, core=None, apps=None, batch=None):
        core = core or MagicMock()
        apps = apps or MagicMock()
        batch = batch or MagicMock()
        mocker.patch.object(k8s_cleanup.client, "CoreV1Api", return_value=core)
        mocker.patch.object(k8s_cleanup.client, "AppsV1Api", return_value=apps)
        mocker.patch.object(k8s_cleanup.client, "BatchV1Api", return_value=batch)
        return core, apps

    def test_true_when_a_statefulset_exists(self, mocker):
        core, apps = self._patch_apis(mocker)
        core.list_namespaced_pod.return_value = _list_result([])
        apps.list_namespaced_deployment.return_value = _list_result([])
        apps.list_namespaced_stateful_set.return_value = _list_result([object()])
        apps.list_namespaced_daemon_set.return_value = _list_result([])
        apps.list_namespaced_replica_set.return_value = _list_result([])

        assert poll_namespace_has_objects("ns", MagicMock()) is True

    def test_false_when_namespace_empty(self, mocker):
        core, apps = self._patch_apis(mocker)
        core.list_namespaced_pod.return_value = _list_result([])
        apps.list_namespaced_deployment.return_value = _list_result([])
        apps.list_namespaced_stateful_set.return_value = _list_result([])
        apps.list_namespaced_daemon_set.return_value = _list_result([])
        apps.list_namespaced_replica_set.return_value = _list_result([])

        assert poll_namespace_has_objects("ns", MagicMock()) is False

    def test_api_exception_is_swallowed(self, mocker):
        core, _ = self._patch_apis(mocker)
        core.list_namespaced_pod.side_effect = ApiException()
        assert poll_namespace_has_objects("ns", MagicMock(), types=["Pod"]) is False


# --------------------------------------------------------------------------- #
# wait_for_no_objs_in_namespace  (loop around poll_namespace_has_objects)
# --------------------------------------------------------------------------- #
class TestWaitForNoObjsInNamespace:
    def test_returns_when_namespace_clears(self, mocker):
        poll = mocker.patch.object(
            k8s_cleanup, "poll_namespace_has_objects", side_effect=[True, False]
        )
        sleep = mocker.patch.object(k8s_cleanup.time, "sleep")

        wait_for_no_objs_in_namespace("ns", api_client=MagicMock())

        assert poll.call_count == 2
        sleep.assert_called_once()

    def test_timeout_raises(self, mocker):
        mocker.patch.object(k8s_cleanup, "poll_namespace_has_objects", return_value=True)
        mocker.patch.object(k8s_cleanup.time, "sleep")

        with pytest.raises(TimeoutError):
            wait_for_no_objs_in_namespace("ns", timeout=-1, api_client=MagicMock())


# --------------------------------------------------------------------------- #
# cleanup_resources  (deletes resources via k8s client)
# --------------------------------------------------------------------------- #
class TestCleanupResources:
    def test_deletes_each_named_statefulset(self, mocker):
        apps = MagicMock()
        mocker.patch.object(k8s_cleanup.client, "AppsV1Api", return_value=apps)

        cleanup_resources({"StatefulSet": ["nodes-0", "nodes-1"]}, "ns", api_client=MagicMock())

        apps.delete_namespaced_stateful_set.assert_any_call("nodes-0", "ns")
        apps.delete_namespaced_stateful_set.assert_any_call("nodes-1", "ns")
        assert apps.delete_namespaced_stateful_set.call_count == 2

    def test_404_is_swallowed(self, mocker):
        core = MagicMock()
        core.delete_namespaced_pod.side_effect = ApiException(status=404)
        mocker.patch.object(k8s_cleanup.client, "CoreV1Api", return_value=core)

        cleanup_resources({"Pod": ["p0"]}, "ns", api_client=MagicMock())  # must not raise

        core.delete_namespaced_pod.assert_called_once_with("p0", "ns")

    def test_controllers_deleted_before_pods(self, mocker):
        manager = MagicMock()
        apps = MagicMock()
        core = MagicMock()
        manager.attach_mock(apps, "apps")
        manager.attach_mock(core, "core")
        mocker.patch.object(k8s_cleanup.client, "AppsV1Api", return_value=apps)
        mocker.patch.object(k8s_cleanup.client, "CoreV1Api", return_value=core)

        cleanup_resources({"Pod": ["p0"], "StatefulSet": ["s0"]}, "ns", api_client=MagicMock())

        names = [c[0] for c in manager.mock_calls]
        assert names.index("apps.delete_namespaced_stateful_set") < names.index(
            "core.delete_namespaced_pod"
        )
